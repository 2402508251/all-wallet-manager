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

CREATE TABLE IF NOT EXISTS transfer_pair_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    out_bill_id INTEGER NOT NULL,
    in_bill_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (out_bill_id) REFERENCES unified_bills(id),
    FOREIGN KEY (in_bill_id) REFERENCES unified_bills(id),
    UNIQUE (out_bill_id, in_bill_id)
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
    file_hash TEXT,
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

CREATE TABLE IF NOT EXISTS ai_provider_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
    model_name TEXT NOT NULL,
    api_base TEXT,
    api_key_enc TEXT,
    temperature REAL NOT NULL DEFAULT 0.2,
    timeout_seconds INTEGER NOT NULL DEFAULT 60,
    max_tokens INTEGER NOT NULL DEFAULT 2048,
    enabled_tasks TEXT NOT NULL DEFAULT '[]',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_payload_json TEXT,
    context_payload_json TEXT,
    result_payload_json TEXT,
    error_message TEXT,
    provider TEXT,
    model_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_parser_rule_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    collection_record_id INTEGER,
    file_name TEXT,
    channel_hint TEXT,
    rule_name TEXT,
    parser_spec_json TEXT NOT NULL,
    sample_preview_json TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'draft',
    reviewer_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES ai_tasks(id),
    FOREIGN KEY (collection_record_id) REFERENCES collection_records(id)
);

CREATE TABLE IF NOT EXISTS ai_category_rule_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    target_category_id INTEGER,
    sample_fields_json TEXT,
    suggestion_json TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'draft',
    reviewer_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES ai_tasks(id),
    FOREIGN KEY (target_category_id) REFERENCES bill_categories(id)
);

CREATE TABLE IF NOT EXISTS ai_report_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    request_text TEXT NOT NULL,
    normalized_spec_json TEXT,
    sql_template TEXT,
    sql_params_json TEXT,
    chart_config_json TEXT,
    explanation TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'draft',
    reviewer_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES ai_tasks(id)
);

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
CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_pair_decisions_pair ON transfer_pair_decisions(out_bill_id, in_bill_id);
CREATE INDEX IF NOT EXISTS idx_transfer_pair_decisions_decision ON transfer_pair_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_source_bills_bill_id ON source_bills(bill_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_batches_batch_id ON import_batches(batch_id);
CREATE INDEX IF NOT EXISTS idx_collection_status ON collection_records(status);
CREATE INDEX IF NOT EXISTS idx_collection_file_hash ON collection_records(source_type, email_config_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_snapshot_details_snapshot ON snapshot_details(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_details_bill ON snapshot_details(bill_id);
CREATE INDEX IF NOT EXISTS idx_role_families_family_id ON role_families(family_id);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON bill_categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_category_keywords_category ON category_keywords(category_id);
CREATE INDEX IF NOT EXISTS idx_category_keywords_field ON category_keywords(match_field);
