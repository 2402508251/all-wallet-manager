"""
数据访问层（DAL）—— 封装 SQLite CRUD 与事务操作
所有操作通过 DatabaseManager 的全局锁串行化，保证单连接线程安全
"""
import sqlite3
import threading
from typing import Optional

from .db import DatabaseManager


class TransactionContext:
    """事务上下文管理器，在 with 块内延迟 commit，退出时统一提交或回滚。
    支持嵌套：通过连接的 in_transaction 属性检测，而非 DAL 实例标志，
    确保不同 DAL 实例共享同一连接时也能正确嵌套。
    """

    def __init__(self, dal: 'DAL'):
        self._dal = dal
        self._lock = dal._lock
        self._is_nested = False
        self._sp_name = None

    def __enter__(self):
        self._lock.acquire()
        conn = self._dal.conn
        if conn.in_transaction:
            self._is_nested = True
            self._dal._transaction_depth += 1
            self._sp_name = f"_sp_{self._dal._transaction_depth}"
            conn.execute(f"SAVEPOINT {self._sp_name}")
        else:
            self._dal._in_transaction = True
            self._dal._transaction_depth = 1
            self._dal._conn_ref = conn
            conn.execute("BEGIN TRANSACTION")
        return self._dal

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = self._dal._conn_ref if self._dal._conn_ref else self._dal.conn
        try:
            if self._is_nested:
                if exc_type is None:
                    conn.execute(f"RELEASE {self._sp_name}")
                else:
                    conn.execute(f"ROLLBACK TO {self._sp_name}")
            else:
                if exc_type is None:
                    conn.commit()
                else:
                    conn.rollback()
        finally:
            if self._is_nested:
                self._dal._transaction_depth -= 1
            else:
                self._dal._in_transaction = False
                self._dal._transaction_depth = 0
                self._dal._conn_ref = None
            self._lock.release()
        return False


class DAL:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._in_transaction = False
        self._transaction_depth = 0
        self._conn_ref = None
        self._tx_lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        return self.db.get_connection()

    @property
    def _lock(self):
        return self.db._lock

    def transaction(self) -> TransactionContext:
        return TransactionContext(self)

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        with self._lock:
            cursor = self.conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            cursor = self.conn.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.conn.execute(sql, params)
            if not self._in_transaction:
                self.conn.commit()
            return cursor

    def insert(self, table: str, data: dict) -> int:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self._lock:
            cursor = self.conn.execute(sql, tuple(data.values()))
            if not self._in_transaction:
                self.conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: dict, where: str, params: tuple = ()) -> int:
        sets = ', '.join([f"{k} = ?" for k in data])
        sql = f"UPDATE {table} SET {sets} WHERE {where}"
        with self._lock:
            cursor = self.conn.execute(sql, tuple(data.values()) + params)
            if not self._in_transaction:
                self.conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, params: tuple = ()) -> int:
        sql = f"DELETE FROM {table} WHERE {where}"
        with self._lock:
            cursor = self.conn.execute(sql, params)
            if not self._in_transaction:
                self.conn.commit()
            return cursor.rowcount

    def count(self, table: str, where: str = "1=1", params: tuple = ()) -> int:
        sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
        with self._lock:
            cursor = self.conn.execute(sql, params)
            return cursor.fetchone()[0]

    def insert_or_ignore(self, table: str, data: dict) -> int:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})"
        with self._lock:
            cursor = self.conn.execute(sql, tuple(data.values()))
            if not self._in_transaction:
                self.conn.commit()
            return cursor.lastrowid

    def bulk_insert(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        columns = list(rows[0].keys())
        col_str = ', '.join(columns)
        placeholders = ', '.join(['?' for _ in columns])
        sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
        values = [tuple(row[c] for c in columns) for row in rows]
        with self._lock:
            cursor = self.conn.executemany(sql, values)
            if not self._in_transaction:
                self.conn.commit()
            return cursor.rowcount

    def bulk_insert_or_ignore(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        columns = list(rows[0].keys())
        col_str = ', '.join(columns)
        placeholders = ', '.join(['?' for _ in columns])
        sql = f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders})"
        values = [tuple(row[c] for c in columns) for row in rows]
        with self._lock:
            cursor = self.conn.executemany(sql, values)
            if not self._in_transaction:
                self.conn.commit()
            return cursor.rowcount

    def paginate(self, table: str, page: int = 1, page_size: int = 20,
                 where: str = "1=1", params: tuple = (),
                 order_by: str = "id DESC") -> dict:
        offset = (page - 1) * page_size
        with self._lock:
            count_sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
            total = self.conn.execute(count_sql, params).fetchone()[0]
            data_sql = f"SELECT * FROM {table} WHERE {where} ORDER BY {order_by} LIMIT ? OFFSET ?"
            cursor = self.conn.execute(data_sql, params + (page_size, offset))
            rows = cursor.fetchall()
        return {
            'list': [dict(r) for r in rows],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size if page_size else 0,
        }