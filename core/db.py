"""
SQLite 数据库连接管理、建表、版本迁移
使用单一共享连接 + 全局锁，避免多线程多连接导致 database is locked
PyWebView 为每个 JS API 调用创建独立线程，threading.local 多连接模式
在 Windows 上极易产生文件锁竞争，改为单连接 + 锁最可靠
"""
import logging
import os
import sqlite3
import threading
import uuid

logger = logging.getLogger(__name__)


class DatabaseManager:
    SCHEMA_VERSION = 6

    def __init__(self, db_path: str, init_sql_path: str | None = None):
        self.db_path = db_path
        self.init_sql_path = init_sql_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'scripts', 'init_db.sql'
        )
        self._lock = threading.RLock()
        self._conn = None

    def initialize(self) -> None:
        conn = self._get_or_create_conn()
        conn.execute("PRAGMA journal_mode = WAL")

        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if cursor.fetchone() is None:
                self._create_tables()
                self._set_version(self.SCHEMA_VERSION)
                self._ensure_default_seed_data(conn)
            else:
                current_version = self._get_version()
                if current_version != self.SCHEMA_VERSION:
                    logger.warning(
                        f"Database schema version mismatch: current={current_version}, expected={self.SCHEMA_VERSION}. "
                        f"Please rebuild the database using init_db.sql script."
                    )
                self._ensure_default_seed_data(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _get_or_create_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            self._conn = conn
        return self._conn

    def _is_connection_valid(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.execute("SELECT 1")
            return True
        except (sqlite3.Error, sqlite3.DatabaseError) as e:
            logger.warning(f"Database connection check failed: {e}")
            return False

    def _reconnect_if_needed(self) -> sqlite3.Connection:
        if not self._is_connection_valid():
            logger.info("Reconnecting to database...")
            self._conn = None
        return self._get_or_create_conn()

    def get_connection(self) -> sqlite3.Connection:
        with self._lock:
            return self._reconnect_if_needed()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                    logger.info("Database connection closed successfully")
                except Exception as e:
                    logger.error(f"Failed to close database connection: {e}")
                self._conn = None

    def execute_in_transaction(self, func) -> any:
        with self._lock:
            conn = self.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                result = func(conn)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def _create_tables(self) -> None:
        conn = self.get_connection()
        with open(self.init_sql_path, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())

    def _insert_default_data(self) -> None:
        conn = self.get_connection()
        self._ensure_default_seed_data(conn)

    def _insert_default_bill_categories(self, conn) -> None:
        categories = [
            (1, "餐饮美食", "🍽️", None, 1, 1, 'system', 1),
            (2, "交通出行", "🚗", None, 1, 2, 'system', 1),
            (3, "购物消费", "🛒", None, 1, 3, 'system', 1),
            (4, "生活缴费", "🏠", None, 1, 4, 'system', 1),
            (5, "通讯网络", "📱", None, 1, 5, 'system', 1),
            (6, "医疗健康", "🏥", None, 1, 6, 'system', 1),
            (7, "教育学习", "📚", None, 1, 7, 'system', 1),
            (8, "休闲娱乐", "🎮", None, 1, 8, 'system', 1),
            (9, "居住房租", "🏡", None, 1, 9, 'system', 1),
            (10, "金融保险", "💰", None, 1, 10, 'system', 1),
            (11, "人情往来", "🎁", None, 1, 11, 'system', 1),
            (12, "收入", "💵", None, 1, 12, 'system', 1),
            (99, "其他支出(未命中)", "📦", None, 1, 99, 'system', 1),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO bill_categories (id, name, icon, parent_id, level, sort_order, source, is_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            categories,
        )

    def _insert_default_system_basics(self, conn) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO families (id, name, is_default) VALUES (1, '默认家庭', 1)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO roles (id, name, role_type) VALUES (1, '未分配', 'personal')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO role_families (role_id, family_id) VALUES (1, 1)"
        )

    def _ensure_default_seed_data(self, conn) -> None:
        self._insert_default_bill_categories(conn)
        self._insert_default_category_match_fields(conn)
        self._insert_default_category_keywords(conn)
        self._insert_default_system_basics(conn)

    def _insert_default_category_match_fields(self, conn) -> None:
        fields = [
            ('counterparty', '交易对方', 'self', 'counterparty', 1, 1, 1),
            ('product_desc', '商品说明', 'self', 'product_desc', 1, 1, 2),
            ('remark', '备注', 'self', 'remark', 1, 1, 3),
            ('all_text', '全部文本', 'self', 'all_text', 1, 1, 4),
            ('initiator_counterparty', '交易对方', 'initiator', 'counterparty', 1, 1, 5),
            ('initiator_product_desc', '商品说明', 'initiator', 'product_desc', 1, 1, 6),
            ('initiator_remark', '备注', 'initiator', 'remark', 1, 1, 7),
            ('initiator_all_text', '全部文本', 'initiator', 'all_text', 1, 1, 8),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO category_match_fields (field_key, label, source_scope, field_expr, is_system, is_enabled, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
            fields,
        )

    def _insert_default_category_keywords(self, conn) -> None:
        rules = [
            (1, '餐饮', 'all_text', 10, 10, 'contains', 1, 'system'),
            (1, '美团', 'all_text', 20, 20, 'contains', 1, 'system'),
            (1, '饿了么', 'all_text', 20, 20, 'contains', 1, 'system'),
            (1, '星巴克', 'all_text', 30, 30, 'contains', 1, 'system'),
            (1, '瑞幸', 'all_text', 30, 30, 'contains', 1, 'system'),
            (2, '滴滴', 'all_text', 25, 20, 'contains', 1, 'system'),
            (2, '地铁', 'all_text', 20, 15, 'contains', 1, 'system'),
            (2, '公交', 'all_text', 20, 15, 'contains', 1, 'system'),
            (3, '淘宝', 'all_text', 25, 20, 'contains', 1, 'system'),
            (3, '京东', 'all_text', 25, 20, 'contains', 1, 'system'),
            (4, '水费', 'all_text', 20, 10, 'contains', 1, 'system'),
            (4, '电费', 'all_text', 20, 10, 'contains', 1, 'system'),
            (5, '话费', 'all_text', 20, 10, 'contains', 1, 'system'),
            (6, '医院', 'all_text', 20, 10, 'contains', 1, 'system'),
            (8, '电影', 'all_text', 20, 10, 'contains', 1, 'system'),
            (10, '保险', 'all_text', 20, 10, 'contains', 1, 'system'),
            (11, '红包', 'all_text', 15, 10, 'contains', 1, 'system'),
        ]
        for category_id, keyword, match_field, weight, priority, match_mode, is_enabled, source in rules:
            exists = conn.execute(
                "SELECT 1 FROM category_keywords WHERE category_id = ? AND keyword = ? AND match_field = ? AND match_mode = ? AND source = ? LIMIT 1",
                (category_id, keyword, match_field, match_mode, source),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO category_keywords
                (category_id, keyword, match_field, weight, priority, match_mode, is_enabled, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (category_id, keyword, match_field, weight, priority, match_mode, is_enabled, source),
            )

    def _get_version(self) -> int:
        cursor = self.get_connection().execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def _set_version(self, version: int) -> None:
        self.get_connection().execute("INSERT INTO schema_version (version) VALUES (?)", (version,))