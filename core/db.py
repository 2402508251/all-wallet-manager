"""
SQLite 数据库连接管理、建表、版本迁移
使用单一共享连接 + 全局锁，避免多线程多连接导致 database is locked
PyWebView 为每个 JS API 调用创建独立线程，threading.local 多连接模式
在 Windows 上极易产生文件锁竞争，改为单连接 + 锁最可靠
"""
import sqlite3
import threading
import uuid


class DatabaseManager:
    SCHEMA_VERSION = 5

    def __init__(self, db_path: str):
        self.db_path = db_path
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
            else:
                current_version = self._get_version()
                if current_version < self.SCHEMA_VERSION:
                    self._migrate(current_version, self.SCHEMA_VERSION)

            self._ensure_schema_v4()
            self._ensure_schema_v5()
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

    def get_connection(self) -> sqlite3.Connection:
        return self._get_or_create_conn()

    def close(self) -> None:
        """关闭数据库连接，释放文件锁"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
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
            merged_into_account_id INTEGER,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (merged_into_account_id) REFERENCES accounts(id),
            UNIQUE (account_tag, channel)
        );

        CREATE TABLE IF NOT EXISTS account_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            alias_value TEXT NOT NULL,
            source_kind TEXT NOT NULL DEFAULT 'manual',
            source_account_id INTEGER,
            merge_session_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            FOREIGN KEY (source_account_id) REFERENCES accounts(id),
            UNIQUE (account_id, channel, alias_type, alias_value)
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
            category_id INTEGER,
            category_source TEXT NOT NULL DEFAULT 'auto',
            category_score INTEGER NOT NULL DEFAULT 0,
            category_rule_id INTEGER,
            is_category_manual_edited INTEGER NOT NULL DEFAULT 0,
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
            merged_group_id TEXT,
            real_payer_account_id INTEGER,
            original_counterparty TEXT,
            original_product_desc TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bill_id) REFERENCES unified_bills(id),
            FOREIGN KEY (credit_account_id) REFERENCES credit_accounts(id),
            FOREIGN KEY (real_payer_account_id) REFERENCES accounts(id)
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
            level INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'user',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES bill_categories(id)
        );

        CREATE TABLE IF NOT EXISTS category_match_fields (
            field_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            field_expr TEXT NOT NULL,
            is_system INTEGER NOT NULL DEFAULT 1,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS category_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            match_field TEXT NOT NULL DEFAULT 'counterparty',
            weight INTEGER NOT NULL DEFAULT 10,
            priority INTEGER NOT NULL DEFAULT 0,
            match_mode TEXT NOT NULL DEFAULT 'contains',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES bill_categories(id),
            FOREIGN KEY (match_field) REFERENCES category_match_fields(field_key)
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
        CREATE INDEX IF NOT EXISTS idx_bills_category_id ON unified_bills(category_id);
        CREATE INDEX IF NOT EXISTS idx_bills_category_source ON unified_bills(category_source);
        CREATE INDEX IF NOT EXISTS idx_bills_category_manual ON unified_bills(is_category_manual_edited);
        CREATE INDEX IF NOT EXISTS idx_bills_assign_status ON unified_bills(assign_status);
        CREATE INDEX IF NOT EXISTS idx_bills_batch_id ON unified_bills(batch_id);
        CREATE INDEX IF NOT EXISTS idx_bills_is_deleted ON unified_bills(is_deleted);
        CREATE INDEX IF NOT EXISTS idx_bills_is_system ON unified_bills(is_system);
        CREATE INDEX IF NOT EXISTS idx_accounts_merged_into ON accounts(merged_into_account_id);
        CREATE INDEX IF NOT EXISTS idx_account_aliases_lookup ON account_aliases(channel, alias_type, alias_value);
        CREATE INDEX IF NOT EXISTS idx_account_aliases_account ON account_aliases(account_id);
        CREATE INDEX IF NOT EXISTS idx_account_aliases_merge_session ON account_aliases(merge_session_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounting_bill_id ON bill_accounting(bill_id);
        CREATE INDEX IF NOT EXISTS idx_accounting_merge_status ON bill_accounting(merge_status);
        CREATE INDEX IF NOT EXISTS idx_accounting_merged_group ON bill_accounting(merged_group_id);
        CREATE INDEX IF NOT EXISTS idx_accounting_real_payer ON bill_accounting(real_payer_account_id);
        CREATE INDEX IF NOT EXISTS idx_accounting_transfer_link ON bill_accounting(transfer_link_id);
        CREATE INDEX IF NOT EXISTS idx_source_bills_bill_id ON source_bills(bill_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_batches_batch_id ON import_batches(batch_id);
        CREATE INDEX IF NOT EXISTS idx_collection_status ON collection_records(status);
        CREATE INDEX IF NOT EXISTS idx_snapshot_details_snapshot ON snapshot_details(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_snapshot_details_bill ON snapshot_details(bill_id);
        CREATE INDEX IF NOT EXISTS idx_role_families_family_id ON role_families(family_id);
        CREATE INDEX IF NOT EXISTS idx_categories_parent ON bill_categories(parent_id);
        CREATE INDEX IF NOT EXISTS idx_category_keywords_category ON category_keywords(category_id);
        CREATE INDEX IF NOT EXISTS idx_category_keywords_field ON category_keywords(match_field);
        """)

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
            ('counterparty', '当前账单-交易对方', 'self', 'counterparty', 1, 1, 1),
            ('product_desc', '当前账单-商品说明', 'self', 'product_desc', 1, 1, 2),
            ('remark', '当前账单-备注', 'self', 'remark', 1, 1, 3),
            ('all_text', '当前账单-全部文本', 'self', 'all_text', 1, 1, 4),
            ('initiator_counterparty', '发起方-交易对方', 'initiator', 'counterparty', 1, 1, 5),
            ('initiator_product_desc', '发起方-商品说明', 'initiator', 'product_desc', 1, 1, 6),
            ('initiator_remark', '发起方-备注', 'initiator', 'remark', 1, 1, 7),
            ('initiator_all_text', '发起方-全部文本', 'initiator', 'all_text', 1, 1, 8),
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

    def _migrate(self, from_version: int, to_version: int) -> None:
        conn = self.get_connection()
        if from_version < 3:
            self._migrate_v2_to_v3(conn)
        # 迁移完成后设置版本
        self._set_version(to_version)

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == column for r in rows)

    def _ensure_schema_v4(self) -> None:
        """确保账户别名与逻辑归并字段存在。

        项目当前主要通过重建数据库应用 schema；这里保留轻量兜底，避免已有开发库
        因缺少新字段无法启动。
        """
        conn = self.get_connection()
        if not self._column_exists(conn, 'accounts', 'merged_into_account_id'):
            conn.execute("ALTER TABLE accounts ADD COLUMN merged_into_account_id INTEGER")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                alias_type TEXT NOT NULL,
                alias_value TEXT NOT NULL,
                source_kind TEXT NOT NULL DEFAULT 'manual',
                source_account_id INTEGER,
                merge_session_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (source_account_id) REFERENCES accounts(id),
                UNIQUE (account_id, channel, alias_type, alias_value)
            )
        """)
        for column_name, column_sql in (
            ('source_kind', "TEXT NOT NULL DEFAULT 'manual'"),
            ('source_account_id', 'INTEGER'),
            ('merge_session_id', 'TEXT'),
        ):
            if not self._column_exists(conn, 'account_aliases', column_name):
                conn.execute(f"ALTER TABLE account_aliases ADD COLUMN {column_name} {column_sql}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_merged_into ON accounts(merged_into_account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_account_aliases_lookup ON account_aliases(channel, alias_type, alias_value)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_account_aliases_account ON account_aliases(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_account_aliases_merge_session ON account_aliases(merge_session_id)")

    def _ensure_schema_v5(self) -> None:
        """确保分类子系统字段存在；项目实际通过重建库应用 schema，这里保留轻量兜底。"""
        conn = self.get_connection()
        for column_name, column_sql in (
            ('category_source', "TEXT NOT NULL DEFAULT 'auto'"),
            ('category_score', 'INTEGER NOT NULL DEFAULT 0'),
            ('category_rule_id', 'INTEGER'),
            ('is_category_manual_edited', 'INTEGER NOT NULL DEFAULT 0'),
        ):
            if not self._column_exists(conn, 'unified_bills', column_name):
                conn.execute(f"ALTER TABLE unified_bills ADD COLUMN {column_name} {column_sql}")
        for column_name, column_sql in (
            ('level', 'INTEGER NOT NULL DEFAULT 1'),
            ('source', "TEXT NOT NULL DEFAULT 'user'"),
            ('is_enabled', 'INTEGER NOT NULL DEFAULT 1'),
            ('created_at', 'TEXT'),
            ('updated_at', 'TEXT'),
        ):
            if not self._column_exists(conn, 'bill_categories', column_name):
                conn.execute(f"ALTER TABLE bill_categories ADD COLUMN {column_name} {column_sql}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS category_match_fields (
                field_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                source_scope TEXT NOT NULL,
                field_expr TEXT NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 1,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
        for column_name, column_sql in (
            ('weight', 'INTEGER NOT NULL DEFAULT 10'),
            ('match_mode', "TEXT NOT NULL DEFAULT 'contains'"),
            ('is_enabled', 'INTEGER NOT NULL DEFAULT 1'),
            ('source', "TEXT NOT NULL DEFAULT 'user'"),
            ('created_at', 'TEXT'),
            ('updated_at', 'TEXT'),
        ):
            if not self._column_exists(conn, 'category_keywords', column_name):
                conn.execute(f"ALTER TABLE category_keywords ADD COLUMN {column_name} {column_sql}")
        conn.execute("UPDATE bill_categories SET level = CASE WHEN parent_id IS NULL THEN 1 ELSE 2 END")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_category_source ON unified_bills(category_source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bills_category_manual ON unified_bills(is_category_manual_edited)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_parent ON bill_categories(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category_keywords_category ON category_keywords(category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category_keywords_field ON category_keywords(match_field)")

    def _migrate_v2_to_v3(self, conn: sqlite3.Connection) -> None:
        """迁移 v2 到 v3：跨平台合并机制重构（不删除账单，使用 merged_group_id）"""
        # 检查是否需要迁移（旧表是否有 merged_to_id 字段）
        if not self._column_exists(conn, 'bill_accounting', 'merged_to_id'):
            # 新表不需要迁移
            return
        
        # 重建 bill_accounting 表，移除旧外键 merged_to_id -> unified_bills.id
        # SQLite 不支持直接删除外键，需要重建表
        
        # 1. 创建新表（不含 merged_to_id 外键）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bill_accounting_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL UNIQUE,
                transfer_link_id TEXT,
                is_credit INTEGER NOT NULL DEFAULT 0,
                credit_account_id INTEGER,
                merge_status TEXT NOT NULL DEFAULT 'normal',
                merged_group_id TEXT,
                real_payer_account_id INTEGER,
                original_counterparty TEXT,
                original_product_desc TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bill_id) REFERENCES unified_bills(id),
                FOREIGN KEY (real_payer_account_id) REFERENCES accounts(id),
                FOREIGN KEY (credit_account_id) REFERENCES credit_accounts(id)
            )
        """)
        
        # 2. 复制数据（处理旧合并记录）
        # 先复制普通记录（包含所有字段）
        try:
            # 尝试复制包含所有字段的数据
            conn.execute("""
                INSERT INTO bill_accounting_new (id, bill_id, transfer_link_id, is_credit, credit_account_id, merge_status, merged_group_id, real_payer_account_id, original_counterparty, original_product_desc, created_at)
                SELECT id, bill_id, transfer_link_id, is_credit, credit_account_id, merge_status, NULL, NULL, original_counterparty, original_product_desc, created_at
                FROM bill_accounting
                WHERE merged_to_id IS NULL OR merge_status NOT IN ('merged_source', 'normal')
            """)
        except sqlite3.OperationalError:
            # 如果旧表缺少某些字段，则只复制基本字段
            conn.execute("""
                INSERT INTO bill_accounting_new (id, bill_id, merge_status, merged_group_id, real_payer_account_id, credit_account_id)
                SELECT id, bill_id, merge_status, NULL, NULL, credit_account_id
                FROM bill_accounting
                WHERE merged_to_id IS NULL OR merge_status NOT IN ('merged_source', 'normal')
            """)
        
        # 3. 处理已合并的记录，生成 merged_group_id
        merged_records = conn.execute(
            "SELECT ba.id, ba.bill_id, ba.merge_status, ba.merged_to_id, ub.is_deleted, ub.account_id "
            "FROM bill_accounting ba "
            "JOIN unified_bills ub ON ba.bill_id = ub.id "
            "WHERE ba.merge_status IN ('merged_source', 'normal') AND ba.merged_to_id IS NOT NULL"
        ).fetchall()
        
        for record in merged_records:
            ba_id = record['id']
            bill_id = record['bill_id']
            merge_status = record['merge_status']
            merged_to_id = record['merged_to_id']
            is_deleted = record['is_deleted']
            
            # 生成 merged_group_id
            group_id = str(uuid.uuid4())
            
            if merge_status == 'merged_source':
                # 恢复被删除的第三方记录（发起方）
                conn.execute(
                    "UPDATE unified_bills SET is_deleted = 0 WHERE id = ?",
                    (bill_id,)
                )
                # 更新发起方账务记录
                conn.execute(
                    "UPDATE bill_accounting_new SET merged_group_id = ?, merge_status = 'merged_source' WHERE id = ?",
                    (group_id, ba_id)
                )
                # 查找真实支付者账户
                target_bill = conn.execute(
                    "SELECT account_id FROM unified_bills WHERE id = ?", (merged_to_id,)
                ).fetchone()
                if target_bill and target_bill['account_id']:
                    conn.execute(
                        "UPDATE bill_accounting_new SET real_payer_account_id = ? WHERE id = ?",
                        (target_bill['account_id'], ba_id)
                    )
            
            elif merge_status == 'normal' and merged_to_id:
                # 更新真实支付者账务记录（银行卡）为 merged_target
                conn.execute(
                    "UPDATE bill_accounting_new SET merged_group_id = ?, merge_status = 'merged_target', real_payer_account_id = ? WHERE id = ?",
                    (group_id, record['account_id'], ba_id)
                )
                # 同时更新发起方的 merged_group_id（它们共享同一组）
                source_ba = conn.execute(
                    "SELECT id FROM bill_accounting_new WHERE bill_id = ?",
                    (merged_to_id,)
                ).fetchone()
                if source_ba:
                    conn.execute(
                        "UPDATE bill_accounting_new SET merged_group_id = ? WHERE id = ?",
                        (group_id, source_ba['id'])
                    )
        
        # 4. 删除旧表
        conn.execute("DROP TABLE bill_accounting")
        
        # 5. 重命名新表
        conn.execute("ALTER TABLE bill_accounting_new RENAME TO bill_accounting")
        
        # 6. 创建索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accounting_merged_group ON bill_accounting(merged_group_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accounting_real_payer ON bill_accounting(real_payer_account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_accounting_bill ON bill_accounting(bill_id)")