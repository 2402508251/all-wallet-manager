"""
数据访问层（DAL）—— 封装 SQLite CRUD 与事务操作
所有操作通过 DatabaseManager 的全局锁串行化，保证单连接线程安全
"""
import sqlite3
from typing import Optional

from .db import DatabaseManager


class DAL:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    @property
    def conn(self) -> sqlite3.Connection:
        return self.db.get_connection()

    @property
    def _lock(self):
        return self.db._lock

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
            self.conn.commit()
            return cursor

    def insert(self, table: str, data: dict) -> int:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self._lock:
            cursor = self.conn.execute(sql, tuple(data.values()))
            self.conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: dict, where: str, params: tuple = ()) -> int:
        sets = ', '.join([f"{k} = ?" for k in data])
        sql = f"UPDATE {table} SET {sets} WHERE {where}"
        with self._lock:
            cursor = self.conn.execute(sql, tuple(data.values()) + params)
            self.conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, params: tuple = ()) -> int:
        sql = f"DELETE FROM {table} WHERE {where}"
        with self._lock:
            cursor = self.conn.execute(sql, params)
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