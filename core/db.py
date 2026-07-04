"""
SQLite 数据库连接管理、建表、版本迁移
使用单一共享连接 + 全局锁，避免多线程多连接导致 database is locked
PyWebView 为每个 JS API 调用创建独立线程，threading.local 多连接模式
在 Windows 上极易产生文件锁竞争，改为单连接 + 锁最可靠
"""
import sqlite3
import threading


class DatabaseManager:
    SCHEMA_VERSION = 2

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = None

    def initialize(self) -> None:
        conn = self._get_or_create_conn()
        conn.execute("PRAGMA journal_mode = WAL")

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if cursor.fetchone() is None:
            self._create_tables()
            self._set_version(self.SCHEMA_VERSION)
            self._insert_default_data()
        else:
            current_version = self._get_version()
            if current_version < self.SCHEMA_VERSION:
                self._migrate(current_version, self.SCHEMA_VERSION)

    def _get_or_create_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            self._conn = conn
        return self._conn

    def get_connection(self) -> sqlite3.Connection:
        return self._get_or_create_conn()

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
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role_type TEXT NOT NULL DEFAULT 'personal',
            is_shared INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS role_families (
            role_id INTEGER NOT NULL,
            family_id INTEGER NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (role_id, family_id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (family_id) REFERENCES families(id)
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            account_tag TEXT,
            channel TEXT NOT NULL,
            role_id INTEGER,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(id),
            UNIQUE (account_tag, channel)
        );

        CREATE TABLE IF NOT EXISTS credit_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            credit_type TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            linked_account_id INTEGER,
            credit_limit_cents INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (linked_account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS unified_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            trade_time TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            counterparty TEXT,
            product_desc TEXT,
            payment_method TEXT,
            status TEXT,
            channel_trade_no TEXT NOT NULL,
            remark TEXT,
            account_id INTEGER,
            role_id INTEGER,
            family_id INTEGER,
            category_id INTEGER,
            assign_status TEXT NOT NULL DEFAULT 'pending',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            is_system INTEGER NOT NULL DEFAULT 0,
            batch_id TEXT NOT NULL,
            source_bill_id INTEGER,
            is_manual_edited INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (family_id) REFERENCES families(id),
            FOREIGN KEY (category_id) REFERENCES bill_categories(id),
            FOREIGN KEY (source_bill_id) REFERENCES source_bills(id),
            UNIQUE (channel, channel_trade_no)
        );

        CREATE TABLE IF NOT EXISTS bill_accounting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL UNIQUE,
            transfer_link_id TEXT,
            is_credit INTEGER NOT NULL DEFAULT 0,
            credit_account_id INTEGER,
            merge_status TEXT NOT NULL DEFAULT 'normal',
            merged_to_id INTEGER,
            original_counterparty TEXT,
            original_product_desc TEXT,
            FOREIGN KEY (bill_id) REFERENCES unified_bills(id),
            FOREIGN KEY (credit_account_id) REFERENCES credit_accounts(id),
            FOREIGN KEY (merged_to_id) REFERENCES unified_bills(id)
        );

        CREATE TABLE IF NOT EXISTS source_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL UNIQUE,
            channel TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bill_id) REFERENCES unified_bills(id)
        );

        CREATE TABLE IF NOT EXISTS import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            channel TEXT NOT NULL,
            file_name TEXT NOT NULL,
            total_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            merged_count INTEGER NOT NULL DEFAULT 0,
            pending_count INTEGER NOT NULL DEFAULT 0,
            unclassified_count INTEGER NOT NULL DEFAULT 0,
            import_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bill_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            icon TEXT,
            parent_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES bill_categories(id)
        );

        CREATE TABLE IF NOT EXISTS category_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            match_field TEXT NOT NULL DEFAULT 'counterparty',
            priority INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES bill_categories(id)
        );

        CREATE TABLE IF NOT EXISTS email_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_addr TEXT NOT NULL,
            imap_server TEXT NOT NULL,
            imap_port INTEGER NOT NULL DEFAULT 993,
            auth_code_enc TEXT NOT NULL,
            last_uid INTEGER,
            last_fetch_ts TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS collection_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            email_config_id INTEGER,
            file_name TEXT NOT NULL,
            file_path TEXT,
            channel TEXT,
            channel_source TEXT NOT NULL DEFAULT 'auto_detect',
            status TEXT NOT NULL DEFAULT 'pending',
            parse_result TEXT,
            batch_id TEXT,
            error_msg TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_config_id) REFERENCES email_configs(id),
            FOREIGN KEY (batch_id) REFERENCES import_batches(batch_id)
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_type TEXT NOT NULL,
            description TEXT,
            bill_count INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS snapshot_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            bill_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            is_deleted_after INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        );
        """)

        conn.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bills_channel_trade_no
            ON unified_bills(channel, channel_trade_no);
        CREATE INDEX IF NOT EXISTS idx_bills_trade_time ON unified_bills(trade_time);
        CREATE INDEX IF NOT EXISTS idx_bills_account_id ON unified_bills(account_id);
        CREATE INDEX IF NOT EXISTS idx_bills_role_id ON unified_bills(role_id);
        CREATE INDEX IF NOT EXISTS idx_bills_family_id ON unified_bills(family_id);
        CREATE INDEX IF NOT EXISTS idx_bills_category_id ON unified_bills(category_id);
        CREATE INDEX IF NOT EXISTS idx_bills_assign_status ON unified_bills(assign_status);
        CREATE INDEX IF NOT EXISTS idx_bills_batch_id ON unified_bills(batch_id);
        CREATE INDEX IF NOT EXISTS idx_bills_is_deleted ON unified_bills(is_deleted);
        CREATE INDEX IF NOT EXISTS idx_bills_is_system ON unified_bills(is_system);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounting_bill_id ON bill_accounting(bill_id);
        CREATE INDEX IF NOT EXISTS idx_accounting_merge_status ON bill_accounting(merge_status);
        CREATE INDEX IF NOT EXISTS idx_accounting_transfer_link ON bill_accounting(transfer_link_id);
        CREATE INDEX IF NOT EXISTS idx_source_bills_bill_id ON source_bills(bill_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_batches_batch_id ON import_batches(batch_id);
        CREATE INDEX IF NOT EXISTS idx_collection_status ON collection_records(status);
        CREATE INDEX IF NOT EXISTS idx_snapshot_details_snapshot ON snapshot_details(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_snapshot_details_bill ON snapshot_details(bill_id);
        CREATE INDEX IF NOT EXISTS idx_role_families_family_id ON role_families(family_id);
        """)

    def _insert_default_data(self) -> None:
        conn = self.get_connection()
        categories = [
            (1, "餐饮美食", "🍽️", None, 1),
            (2, "交通出行", "🚗", None, 2),
            (3, "购物消费", "🛒", None, 3),
            (4, "生活缴费", "🏠", None, 4),
            (5, "通讯网络", "📱", None, 5),
            (6, "医疗健康", "🏥", None, 6),
            (7, "教育学习", "📚", None, 7),
            (8, "休闲娱乐", "🎮", None, 8),
            (9, "居住房租", "🏡", None, 9),
            (10, "金融保险", "💰", None, 10),
            (11, "人情往来", "🎁", None, 11),
            (99, "其他支出", "📦", None, 99),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO bill_categories (id, name, icon, parent_id, sort_order) VALUES (?, ?, ?, ?, ?)",
            categories,
        )
        conn.execute(
            "INSERT OR IGNORE INTO families (id, name, is_default) VALUES (1, '默认家庭', 1)"
        )

    def _get_version(self) -> int:
        cursor = self.get_connection().execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def _set_version(self, version: int) -> None:
        self.get_connection().execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    def _migrate(self, from_version: int, to_version: int) -> None:
        conn = self.get_connection()
        if from_version < 2:
            self._migrate_v1_to_v2(conn)

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == column for r in rows)

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS role_families (
            role_id INTEGER NOT NULL,
            family_id INTEGER NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (role_id, family_id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (family_id) REFERENCES families(id)
        )
        """)

        if self._column_exists(conn, 'roles', 'family_id'):
            conn.execute("""
            INSERT OR IGNORE INTO role_families (role_id, family_id, is_primary)
                SELECT id, family_id, 1 FROM roles WHERE family_id IS NOT NULL
            """)

        if not self._column_exists(conn, 'unified_bills', 'family_id'):
            conn.execute("ALTER TABLE unified_bills ADD COLUMN family_id INTEGER REFERENCES families(id)")

        if not self._column_exists(conn, 'unified_bills', 'is_system'):
            conn.execute("ALTER TABLE unified_bills ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")

        conn.execute("""
        UPDATE unified_bills SET family_id = (
            SELECT rf.family_id FROM accounts a
            JOIN role_families rf ON rf.role_id = a.role_id AND rf.is_primary = 1
            WHERE a.id = unified_bills.account_id
        ) WHERE family_id IS NULL AND account_id IS NOT NULL
        """)

        if not self._column_exists(conn, 'bill_accounting', 'original_counterparty'):
            conn.execute("ALTER TABLE bill_accounting ADD COLUMN original_counterparty TEXT")

        if not self._column_exists(conn, 'bill_accounting', 'original_product_desc'):
            conn.execute("ALTER TABLE bill_accounting ADD COLUMN original_product_desc TEXT")

        if not self._column_exists(conn, 'snapshot_details', 'is_deleted_after'):
            conn.execute("ALTER TABLE snapshot_details ADD COLUMN is_deleted_after INTEGER NOT NULL DEFAULT 0")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_role_id ON unified_bills(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_is_system ON unified_bills(is_system)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_families_family_id ON role_families(family_id)")