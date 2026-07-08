"""
PyWebView API 桥接 —— 注册所有暴露给前端的方法
所有 API 方法统一返回格式：{ success: bool, data: any, message: str }
所有 API 方法统一接收 params 字典参数（PyWebView 传参机制）
"""
import json
import logging
import os
import uuid
from datetime import datetime, date


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%dT%H:%M:%S')
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        return super().default(obj)

from core.db import DatabaseManager
from core.config_manager import ConfigManager
from core.dal import DAL
from core.db_rebuild import rebuild_database
from core.snapshot import SnapshotEngine
from core.crypto_utils import CredentialEncryptor


logger = logging.getLogger(__name__)

VALID_TRADE_TYPES = {
    'consumption',
    'credit_consumption',
    'refund',
    'transfer_out',
    'transfer_in',
    'repayment',
    'repayment_mirror',
    'fee',
    'topup',
    'withdrawal',
    'investment',
    'other',
}


class ApiBridge:
    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager, app_dir: str):
        self.db = db_manager
        self.config = config_manager
        self.dal = DAL(db_manager)
        self.app_dir = app_dir
        self.snapshot = SnapshotEngine(db_manager, dal=self.dal)
        self.encryptor = CredentialEncryptor()
        self._account_cache = {}
        self._default_ids = None  # 缓存默认 family/role，避免重复查询

    def ok(self, data=None, message='') -> dict:
        return {'success': True, 'data': data, 'message': message}

    def err(self, message='操作失败') -> dict:
        return {'success': False, 'data': None, 'message': message}

    def start_task(self) -> dict:
        task_id = str(uuid.uuid4())
        return {'success': True, 'data': {'task_id': task_id}, 'message': ''}

    def _now(self) -> str:
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

    def _normalize_trade_type(self, trade_type):
        value = str(trade_type or '').strip()
        if not value:
            return None
        if value == 'mirror':
            value = 'repayment_mirror'
        return value

    def _ensure_bill_accounting_row(self, bill_id: int, data=None) -> dict:
        existing = self.dal.fetch_one("SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,))
        payload = {'merge_status': 'normal'}
        if data:
            payload.update(data)
        if existing:
            self.dal.update('bill_accounting', payload, 'bill_id = ?', (bill_id,))
        else:
            payload['bill_id'] = bill_id
            self.dal.insert('bill_accounting', payload)
        return self.dal.fetch_one("SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,)) or {}

    def _apply_accounting_pipeline(self, bill: dict, now: str | None = None) -> dict:
        now = now or self._now()
        bill_id = bill.get('id')
        if not bill_id:
            return {'post_actions': []}

        self._ensure_bill_accounting_row(bill_id, {'created_at': now})
        existing_accounting = self.dal.fetch_one("SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,)) or {}
        post_actions = []

        from modules.accounting.credit_tracker import CreditTracker
        credit_tracker = CreditTracker(self.dal)
        credit_result = credit_tracker.identify_credit(bill)
        if credit_result:
            unified_updates = {}
            if credit_result.get('trade_type') and bill.get('trade_type') != credit_result['trade_type']:
                unified_updates['trade_type'] = credit_result['trade_type']
                bill['trade_type'] = credit_result['trade_type']
            if unified_updates:
                unified_updates['updated_at'] = now
                self.dal.update('unified_bills', unified_updates, 'id = ?', (bill_id,))
            self._ensure_bill_accounting_row(bill_id, {
                'is_credit': 1,
                'credit_account_id': credit_result.get('credit_account_id'),
            })
            bill['is_credit'] = True
            bill['credit_account_id'] = credit_result.get('credit_account_id')
            post_actions.append('credit_identified')

        if bill.get('trade_type') == 'repayment':
            repayment_link = None
            if existing_accounting.get('transfer_link_id') and existing_accounting.get('credit_account_id'):
                repayment_link = {
                    'credit_account_id': existing_accounting.get('credit_account_id'),
                    'transfer_link_id': existing_accounting.get('transfer_link_id'),
                    'is_credit': 0,
                }
            else:
                repayment_link = credit_tracker.link_repayment(bill)
            if repayment_link:
                self._ensure_bill_accounting_row(bill_id, repayment_link)
                bill.update(repayment_link)
                mirror_trade_no = f"MIRROR_{bill.get('channel_trade_no', '')}"
                existing_mirror = self.dal.fetch_one(
                    "SELECT id FROM unified_bills WHERE channel = ? AND channel_trade_no = ?",
                    (bill.get('channel', ''), mirror_trade_no),
                )
                if not existing_mirror:
                    mirror = credit_tracker.generate_mirror_record({**bill, **repayment_link})
                    mirror['created_at'] = now
                    mirror['updated_at'] = now
                    mirror_id = self.dal.insert('unified_bills', mirror)
                    self._ensure_bill_accounting_row(mirror_id, {
                        'transfer_link_id': repayment_link.get('transfer_link_id'),
                        'credit_account_id': repayment_link.get('credit_account_id'),
                        'is_credit': 0,
                        'created_at': now,
                    })
                post_actions.append('repayment_mirror_created')

        merge_result = None
        if bill.get('channel') in ('wechat', 'alipay'):
            from modules.accounting.cross_platform_merger import CrossPlatformMerger
            merger = CrossPlatformMerger(self.dal)
            merge_result = merger.mark_orphan(dict(bill)) or {}
            if merge_result.get('merged'):
                post_actions.append('auto_merged_source')
            elif merge_result.get('orphan'):
                post_actions.append('mark_orphan')
        elif bill.get('channel') == 'ccb':
            from modules.accounting.cross_platform_merger import CrossPlatformMerger
            merger = CrossPlatformMerger(self.dal)
            merge_result = merger.try_merge(dict(bill)) or {}
            if merge_result.get('merged'):
                post_actions.append('auto_merged_target')

        if bill.get('trade_type') in ('transfer_out', 'transfer_in'):
            accounting = self.dal.fetch_one(
                "SELECT transfer_link_id FROM bill_accounting WHERE bill_id = ?", (bill_id,)
            )
            if not accounting or not accounting.get('transfer_link_id'):
                from modules.accounting.transfer_pairer import TransferPairer
                pairer = TransferPairer(self.dal)
                transfer_result = pairer.auto_pair_strong(dict(bill))
                if transfer_result and transfer_result.get('transfer_link_id'):
                    post_actions.append('auto_transfer_paired')

        if not post_actions:
            post_actions.append('normal_only')
        return {'post_actions': post_actions}

    def ensure_default_family_and_role(self) -> dict:
        if self._default_ids is not None:
            cached_family = self.dal.fetch_one(
                "SELECT id FROM families WHERE id = ?", (self._default_ids['family_id'],)
            )
            cached_role = self.dal.fetch_one(
                "SELECT id FROM roles WHERE id = ?", (self._default_ids['role_id'],)
            )
            if cached_family and cached_role:
                return self._default_ids
            logger.warning("default family/role cache invalidated: %s", self._default_ids)
            self._default_ids = None

        def ensure_rows():
            family = self.dal.fetch_one(
                "SELECT id FROM families WHERE name = '默认家庭'"
            )
            if not family:
                family_id = self.dal.insert('families', {'name': '默认家庭', 'is_default': 1})
            else:
                family_id = family['id']

            role = self.dal.fetch_one(
                "SELECT id FROM roles WHERE name = '未分配'"
            )
            if not role:
                role_id = self.dal.insert('roles', {
                    'name': '未分配',
                    'role_type': 'personal',
                })
            else:
                role_id = role['id']

            existing_rf = self.dal.fetch_one(
                "SELECT 1 FROM role_families WHERE role_id = ? AND family_id = ?",
                (role_id, family_id),
            )
            if not existing_rf:
                self.dal.insert('role_families', {
                    'role_id': role_id,
                    'family_id': family_id,
                })
            return {'role_id': role_id, 'family_id': family_id}

        if self.dal.conn.in_transaction:
            self._default_ids = ensure_rows()
        else:
            with self.dal.transaction():
                self._default_ids = ensure_rows()
        return self._default_ids

    def _resolve_canonical_account_id(self, account_id: int) -> int:
        """沿 merged_into_account_id 解析到账户规范 ID。"""
        if not account_id:
            return account_id
        seen = set()
        current_id = account_id
        while current_id and current_id not in seen:
            seen.add(current_id)
            row = self.dal.fetch_one(
                "SELECT merged_into_account_id FROM accounts WHERE id = ?",
                (current_id,),
            )
            if not row or not row.get('merged_into_account_id'):
                return current_id
            current_id = row['merged_into_account_id']
        return account_id

    def _add_wechat_alias(
        self,
        account_id: int,
        alias_value: str,
        alias_type: str = 'wechat_nickname',
        source_kind: str = 'import',
        source_account_id: int = None,
        merge_session_id: str = None,
    ) -> None:
        alias_value = str(alias_value or '').strip()
        if not account_id or not alias_value or alias_value == '未知用户':
            return
        try:
            self.dal.insert_or_ignore('account_aliases', {
                'account_id': account_id,
                'channel': 'wechat',
                'alias_type': alias_type,
                'alias_value': alias_value,
                'source_kind': source_kind,
                'source_account_id': source_account_id,
                'merge_session_id': merge_session_id,
                'created_at': self._now(),
            })
        except Exception as e:
            logger.warning("add_wechat_alias failed: account_id=%s alias=%s error=%s", account_id, alias_value, e)

    def get_or_create_account(self, account_tag: str, account_name: str, channel: str, hints: dict = None) -> int:
        hints = hints or {}
        cache_alias = '|'.join(sorted(str(v).strip() for v in hints.get('alias_candidates', []) if str(v).strip()))
        cache_key = f"{account_tag}|{channel}|{cache_alias}"
        if cache_key in self._account_cache:
            return self._account_cache[cache_key]

        account = self.dal.fetch_one(
            "SELECT id FROM accounts WHERE account_tag = ? AND channel = ?",
            (account_tag, channel),
        )
        if account:
            account_id = self._resolve_canonical_account_id(account['id'])
            if channel == 'wechat':
                for alias in hints.get('alias_candidates', []):
                    self._add_wechat_alias(account_id, alias)
            self._account_cache[cache_key] = account_id
            return account_id

        if channel == 'wechat':
            for alias in hints.get('alias_candidates', []):
                alias_value = str(alias or '').strip()
                if not alias_value:
                    continue
                alias_row = self.dal.fetch_one(
                    "SELECT account_id FROM account_aliases "
                    "WHERE channel = 'wechat' AND alias_value = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (alias_value,),
                )
                if alias_row:
                    account_id = self._resolve_canonical_account_id(alias_row['account_id'])
                    self._add_wechat_alias(account_id, alias_value)
                    self._account_cache[cache_key] = account_id
                    return account_id

        # 确保默认角色存在，新账户自动关联
        defaults = self.ensure_default_family_and_role()
        default_role_id = defaults['role_id']

        account_id = self.dal.insert('accounts', {
            'account_name': account_name,
            'account_tag': account_tag,
            'channel': channel,
            'role_id': default_role_id,
        })

        if channel == 'wechat':
            for alias in hints.get('alias_candidates', []):
                self._add_wechat_alias(account_id, alias)

        self._account_cache[cache_key] = account_id
        return account_id

    # ─── 6.2.1 采集相关 ────────────────────────────

    def select_files(self, params=None) -> dict:
        import webview
        try:
            window = webview.windows[0]
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=(
                    '账单文件 (*.xlsx;*.xls;*.csv;*.zip;*.pdf)',
                    '所有文件 (*.*)',
                ),
            )
            if not result:
                return self.ok({'paths': []})
            return self.ok({'paths': list(result)})
        except Exception as e:
            return self.err(f'文件选择失败: {e}')

    def upload_files(self, params=None) -> dict:
        files = (params or {}).get('files', [])
        from modules.collection.file_upload import FileUploadHandler
        handler = FileUploadHandler(self.app_dir, self.dal)
        try:
            record_ids = handler.handle_upload(files)
            return self.ok({'record_ids': record_ids, 'count': len(record_ids)})
        except Exception as e:
            return self.err(f'上传失败: {e}')

    def set_zip_password(self, params=None) -> dict:
        p = params or {}
        record_id = p.get('record_id')
        password = p.get('password', '')
        from modules.collection.file_upload import FileUploadHandler
        handler = FileUploadHandler(self.app_dir, self.dal)
        try:
            result = handler.handle_zip_password(record_id, password)
            if result.get('success'):
                return self.ok(result)
            return self.err(result.get('message', '解压失败'))
        except Exception as e:
            return self.err(f'解压失败: {e}')

    def parse_collection(self, params=None) -> dict:
        record_id = (params or {}).get('record_id')
        record = self.dal.fetch_one(
            "SELECT * FROM collection_records WHERE id = ?", (record_id,)
        )
        if not record:
            return self.err('记录不存在')

        channel = record['channel']
        if channel == 'unknown':
            return self.err('渠道未识别，请手动指定')

        file_path = record['file_path']
        if not file_path or not os.path.exists(file_path):
            return self.err('文件不存在')

        try:
            from modules.parser.parser_factory import ParserFactory
            parser = ParserFactory.get_parser(channel, self.config)
            result = parser.parse(file_path)

            if result.errors:
                self.dal.update(
                    'collection_records',
                    {'status': 'error', 'error_msg': '; '.join(result.errors)},
                    'id = ?',
                    (record_id,),
                )
                return self.err('; '.join(result.errors))

            from modules.attribution.account_extractor import AccountExtractor
            extractor = AccountExtractor()
            account_info = extractor.extract(channel, file_path)

            batch_id = str(uuid.uuid4())
            now = self._now()

            success_count = 0
            duplicate_count = 0
            classified_count = 0
            unclassified_count = 0

            from modules.categorizer import CategoryService
            category_service = CategoryService(self.dal)

            with self.dal.transaction():
                payment_method_to_account = {}
                balance_account_id = None
                for acc in account_info.get('accounts', []):
                    account_id = self.get_or_create_account(
                        acc['tag'], acc['name'], channel, acc
                    )
                    payment_method_to_account[acc['payment_method']] = account_id
                    if acc.get('payment_method_type') == 'balance' and balance_account_id is None:
                        balance_account_id = account_id

                for i, rec in enumerate(result.records):
                    existing = self.dal.fetch_one(
                        "SELECT id FROM unified_bills WHERE channel = ? AND channel_trade_no = ?",
                        (rec['channel'], rec['channel_trade_no']),
                    )
                    if existing:
                        duplicate_count += 1
                        continue

                    payment_method = rec.get('payment_method', '')
                    account_id = payment_method_to_account.get(payment_method)
                    if not account_id:
                        for pm, aid in payment_method_to_account.items():
                            if pm in payment_method or payment_method in pm:
                                account_id = aid
                                break
                    if (
                        not account_id
                        and rec.get('channel') in ('wechat', 'alipay')
                        and rec.get('direction') == 'income'
                        and balance_account_id
                    ):
                        account_id = balance_account_id
                        logger.info(
                            "parse_collection assigned income bill to balance account: channel=%s trade_no=%s payment_method=%s account_id=%s",
                            rec.get('channel'), rec.get('channel_trade_no'), payment_method, account_id,
                        )
                    if not account_id and '_default_' in payment_method_to_account:
                        account_id = payment_method_to_account['_default_']

                    role_id = None
                    if account_id:
                        account = self.dal.fetch_one(
                            "SELECT role_id FROM accounts WHERE id = ?", (account_id,)
                        )
                        if not account:
                            logger.warning(
                                "parse_collection ignored invalid account_id=%s record_id=%s trade_no=%s",
                                account_id, record_id, rec.get('channel_trade_no'),
                            )
                            account_id = None
                        elif account['role_id']:
                            role = self.dal.fetch_one(
                                "SELECT id FROM roles WHERE id = ?", (account['role_id'],)
                            )
                            if role:
                                role_id = account['role_id']
                            else:
                                logger.warning(
                                    "parse_collection ignored invalid role_id=%s for account_id=%s record_id=%s trade_no=%s",
                                    account['role_id'], account_id, record_id, rec.get('channel_trade_no'),
                                )

                    assign_status = 'assigned' if (account_id and role_id) else 'pending'

                    bill_data = {
                        'channel': rec['channel'],
                        'trade_time': rec['trade_time'],
                        'trade_type': rec['trade_type'],
                        'direction': rec['direction'],
                        'amount_cents': rec['amount_cents'],
                        'counterparty': rec.get('counterparty', ''),
                        'product_desc': rec.get('product_desc', ''),
                        'payment_method': payment_method,
                        'status': rec.get('status', ''),
                        'channel_trade_no': rec['channel_trade_no'],
                        'remark': rec.get('remark', ''),
                        'account_id': account_id,
                        'role_id': role_id,
                        'assign_status': assign_status,
                        'is_system': 0,
                        'batch_id': batch_id,
                        'created_at': now,
                        'updated_at': now,
                    }
                    bill_id = self.dal.insert('unified_bills', bill_data)
                    imported_bill = {**bill_data, 'id': bill_id}

                    if i < len(result.raw_records):
                        raw = result.raw_records[i]
                        self.dal.insert('source_bills', {
                            'bill_id': bill_id,
                            'channel': rec['channel'],
                            'raw_json': json.dumps(raw.get('raw', {}), ensure_ascii=False, cls=DateTimeEncoder),
                            'created_at': now,
                        })

                    pipeline_result = self._apply_accounting_pipeline(imported_bill, now)
                    post_action = ','.join(pipeline_result.get('post_actions', ['normal_only']))

                    logger.info(
                        "parse_collection post_action=%s bill_id=%s channel=%s batch_id=%s",
                        post_action, bill_id, rec['channel'], batch_id,
                    )

                    category_result = category_service.categorize_bill(bill_id, bill=imported_bill)
                    category_service.apply_result(bill_id, category_result)
                    if category_result.matched:
                        classified_count += 1
                    else:
                        unclassified_count += 1

                    success_count += 1

                self.dal.insert('import_batches', {
                    'batch_id': batch_id,
                    'source': record['source_type'],
                    'channel': channel,
                    'file_name': record['file_name'],
                    'total_count': result.total,
                    'success_count': success_count,
                    'duplicate_count': duplicate_count,
                    'unclassified_count': unclassified_count,
                    'import_time': now,
                })

                self.dal.update(
                    'collection_records',
                    {'status': 'parsed', 'batch_id': batch_id,
                     'parse_result': json.dumps({
                         'total': result.total,
                         'success': success_count,
                         'duplicate': duplicate_count,
                         'classified': classified_count,
                         'unclassified': unclassified_count,
                         'accounts_created': len(account_info.get('accounts', [])),
                     })},
                    'id = ?',
                    (record_id,),
                )

            return self.ok({
                'batch_id': batch_id,
                'total': result.total,
                'success': success_count,
                'duplicate': duplicate_count,
                'classified': classified_count,
                'unclassified': unclassified_count,
                'accounts_created': len(account_info.get('accounts', [])),
            })

        except Exception as e:
            try:
                self.dal.update(
                    'collection_records',
                    {'status': 'error', 'error_msg': str(e)},
                    'id = ?',
                    (record_id,),
                )
            except Exception:
                pass
            return self.err(f'解析失败: {e}')

    def parse_batch(self, params=None) -> dict:
        record_ids = (params or {}).get('record_ids', [])
        results = []
        for rid in record_ids:
            r = self.parse_collection({'record_id': rid})
            results.append({'record_id': rid, **r})
        return self.ok({'results': results})

    def set_channel_manual(self, params=None) -> dict:
        p = params or {}
        record_id = p.get('record_id')
        channel = p.get('channel', '')
        if channel not in ('wechat', 'alipay', 'ccb'):
            return self.err('无效渠道')
        self.dal.update(
            'collection_records',
            {'channel': channel, 'channel_source': 'manual'},
            'id = ?',
            (record_id,),
        )
        return self.ok()

    def get_collection_list(self, params=None) -> dict:
        p = params or {}
        page = p.get('page', 1)
        page_size = p.get('page_size', 20)
        offset = (page - 1) * page_size
        total = self.dal.count('collection_records')
        rows = self.dal.fetch_all(
            "SELECT * FROM collection_records ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        return self.ok({'total': total, 'list': [dict(r) for r in rows]})

    # ─── 6.2.2 邮箱相关 ────────────────────────────

    def save_email_config(self, params=None) -> dict:
        p = params or {}
        email = p.get('email', '')
        imap_server = p.get('imap_server', '')
        imap_port = p.get('imap_port', 993)
        auth_code = p.get('auth_code', '')
        encrypted = self.encryptor.encrypt(auth_code)
        cid = self.dal.insert('email_configs', {
            'email_addr': email,
            'imap_server': imap_server,
            'imap_port': imap_port,
            'auth_code_enc': encrypted,
            'created_at': self._now(),
        })
        return self.ok({'config_id': cid})

    def test_email_connection(self, params=None) -> dict:
        config_id = (params or {}).get('config_id')
        from modules.collection.email_fetch import EmailFetcher
        fetcher = EmailFetcher(self.app_dir, self.dal, self.config)
        return fetcher.test_connection(config_id)

    def fetch_email_bills(self, params=None) -> dict:
        config_id = (params or {}).get('config_id')
        from modules.collection.email_fetch import EmailFetcher
        fetcher = EmailFetcher(self.app_dir, self.dal, self.config)
        return fetcher.fetch_bills(config_id)

    def clear_email_credentials(self, params=None) -> dict:
        config_id = (params or {}).get('config_id')
        from modules.collection.email_fetch import EmailFetcher
        fetcher = EmailFetcher(self.app_dir, self.dal, self.config)
        success = fetcher.clear_credentials(config_id)
        return self.ok() if success else self.err('删除失败')

    def get_email_configs(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT id, email_addr, imap_server, imap_port, last_uid, last_fetch_ts, created_at FROM email_configs"
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def delete_email_config(self, params=None) -> dict:
        config_id = (params or {}).get('config_id')
        deleted = self.dal.delete('email_configs', 'id = ?', (config_id,))
        return self.ok() if deleted else self.err('删除失败')

    # ─── 6.2.3 账单查询 ────────────────────────────

    def query_bills(self, params=None) -> dict:
        p = params or {}
        filters = p.get('filters')
        page = p.get('page', 1)
        page_size = p.get('page_size', 20)

        conditions = ["ub.is_deleted = 0"]
        sql_params = []

        if filters:
            if filters.get('channel'):
                conditions.append("ub.channel = ?")
                sql_params.append(filters['channel'])
            if filters.get('direction'):
                conditions.append("ub.direction = ?")
                sql_params.append(filters['direction'])
            if filters.get('trade_type'):
                trade_type = self._normalize_trade_type(filters['trade_type'])
                conditions.append("ub.trade_type = ?")
                sql_params.append(trade_type)
            if filters.get('start_time'):
                conditions.append("ub.trade_time >= ?")
                sql_params.append(filters['start_time'])
            if filters.get('end_time'):
                conditions.append("ub.trade_time <= ?")
                sql_params.append(filters['end_time'])
            if filters.get('family_id'):
                conditions.append(
                    "EXISTS (SELECT 1 FROM role_families rf WHERE rf.role_id = ub.role_id AND rf.family_id = ?)"
                )
                sql_params.append(filters['family_id'])
            if filters.get('role_id'):
                conditions.append("ub.role_id = ?")
                sql_params.append(filters['role_id'])
            if filters.get('account_id'):
                conditions.append("ub.account_id = ?")
                sql_params.append(filters['account_id'])
            if filters.get('assign_status'):
                conditions.append("ub.assign_status = ?")
                sql_params.append(filters['assign_status'])
            if filters.get('merge_status'):
                conditions.append("ba.merge_status = ?")
                sql_params.append(filters['merge_status'])
            if filters.get('category_id'):
                conditions.append("ub.category_id = ?")
                sql_params.append(filters['category_id'])
            if filters.get('keyword'):
                conditions.append("(ub.counterparty LIKE ? OR ub.product_desc LIKE ? OR ub.remark LIKE ?)")
                kw = f"%{filters['keyword']}%"
                sql_params.extend([kw, kw, kw])
            if filters.get('is_deleted') is not None:
                conditions[0] = f"ub.is_deleted = {int(filters['is_deleted'])}"

        has_merge_filter = filters.get('merge_status') if filters else False
        join_clause = " LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id " if has_merge_filter else ""

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        total = self.dal.fetch_one(
            f"SELECT COUNT(*) as cnt FROM unified_bills ub{join_clause} WHERE {where}",
            tuple(sql_params),
        )['cnt']

        rows = self.dal.fetch_all(
            f"SELECT ub.*, ba.merge_status, ba.transfer_link_id, ba.is_credit, "
            f"ba.credit_account_id, ca.account_name AS credit_account_name, "
            f"bc.name as category_name "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"LEFT JOIN credit_accounts ca ON ba.credit_account_id = ca.id "
            f"LEFT JOIN bill_categories bc ON ub.category_id = bc.id "
            f"WHERE {where} ORDER BY ub.trade_time DESC LIMIT ? OFFSET ?",
            tuple(sql_params) + (page_size, offset),
        )

        return self.ok({'total': total, 'list': [dict(r) for r in rows]})

    def get_bill_detail(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        bill = self.dal.fetch_one(
            "SELECT ub.*, ba.merge_status, ba.transfer_link_id, "
            "ba.is_credit, ba.credit_account_id, ca.account_name AS credit_account_name, "
            "ba.merged_group_id, ba.real_payer_account_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "LEFT JOIN credit_accounts ca ON ba.credit_account_id = ca.id "
            "WHERE ub.id = ?",
            (bill_id,),
        )
        if not bill:
            return self.err('账单不存在')

        source = self.dal.fetch_one(
            "SELECT * FROM source_bills WHERE bill_id = ?", (bill_id,)
        )

        result = dict(bill)
        if source:
            result['source_bill'] = {
                'channel': source['channel'],
                'raw_json': source['raw_json'],
            }

        return self.ok(result)

    def update_bill(self, params=None) -> dict:
        p = params or {}
        bill_id = p.get('bill_id')
        fields = p.get('fields', {})
        bill = self.dal.fetch_one(
            "SELECT is_system FROM unified_bills WHERE id = ?", (bill_id,)
        )
        if not bill:
            return self.err('账单不存在')
        if bill['is_system'] == 1:
            return self.err('系统生成的记录不可编辑')

        allowed = {
            'counterparty', 'product_desc', 'payment_method', 'remark',
            'trade_type', 'direction', 'category_id', 'assign_status',
            'account_id', 'role_id',
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return self.err('无有效更新字段')

        if 'trade_type' in data:
            trade_type = self._normalize_trade_type(data.get('trade_type'))
            if trade_type is None:
                data['trade_type'] = None
            elif trade_type not in VALID_TRADE_TYPES:
                return self.err('交易类型无效')
            else:
                data['trade_type'] = trade_type

        if 'category_id' in data:
            data['is_category_manual_edited'] = 1
            data['category_source'] = 'manual'
            data['category_score'] = 0
            data['category_rule_id'] = None
        data['is_manual_edited'] = 1
        data['updated_at'] = self._now()

        self.dal.update('unified_bills', data, 'id = ?', (bill_id,))
        return self.ok()

    def batch_update_bills(self, params=None) -> dict:
        p = params or {}
        bill_ids = p.get('bill_ids', [])
        fields = p.get('fields', {})
        if not bill_ids:
            return self.err('未指定账单')

        allowed = {
            'category_id', 'assign_status', 'account_id', 'role_id',
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return self.err('无有效更新字段')

        if 'category_id' in data:
            data['is_category_manual_edited'] = 1
            data['category_source'] = 'manual'
            data['category_score'] = 0
            data['category_rule_id'] = None
        data['updated_at'] = self._now()
        placeholders = ', '.join(['?' for _ in bill_ids])
        updated = self.dal.update(
            'unified_bills',
            data,
            f'id IN ({placeholders})',
            tuple(bill_ids),
        )
        return self.ok({'updated': updated})

    # ─── 6.2.4 账务处理 ────────────────────────────

    def get_orphan_records(self, params=None) -> dict:
        p = params or {}
        page = p.get('page', 1)
        page_size = p.get('page_size', 20)
        from modules.accounting.cross_platform_merger import CrossPlatformMerger
        merger = CrossPlatformMerger(self.dal)
        orphans = merger.scan_orphans()
        offset = (page - 1) * page_size
        paged = orphans[offset:offset + page_size]
        return self.ok({'total': len(orphans), 'list': paged})

    def get_merged_records(self, params=None) -> dict:
        """获取已合并的记录列表（按 merged_group_id 分组展示）"""
        p = params or {}
        page = p.get('page', 1)
        page_size = p.get('page_size', 50)
        # 查询发起方记录（merged_source），展示合并组
        rows = self.dal.fetch_all(
            "SELECT ub.id, ub.trade_time, ub.channel, ub.counterparty, ub.product_desc, "
            "ub.amount_cents, ba.merged_group_id, ba.real_payer_account_id, "
            "a.account_name as real_payer_name "
            "FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "LEFT JOIN accounts a ON ba.real_payer_account_id = a.id "
            "WHERE ba.merge_status = 'merged_source' AND ub.is_deleted = 0 "
            "ORDER BY ub.trade_time DESC"
        )
        offset = (page - 1) * page_size
        paged = rows[offset:offset + page_size]
        return self.ok({'total': len(rows), 'list': [dict(r) for r in paged]})

    def confirm_orphan_independent(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        self.dal.update(
            'bill_accounting',
            {'merge_status': 'normal'},
            'bill_id = ? AND merge_status = ?',
            (bill_id, 'orphan'),
        )
        return self.ok()

    def undo_merge(self, params=None) -> dict:
        merged_group_id = (params or {}).get('merged_group_id')
        from modules.accounting.cross_platform_merger import CrossPlatformMerger
        merger = CrossPlatformMerger(self.dal)
        result = merger.undo_merge(merged_group_id)
        if result.get('success'):
            return self.ok(result)
        return self.err(result.get('message', '撤销失败'))

    def try_merge_orphan(self, params=None) -> dict:
        """尝试为孤儿记录查找匹配的银行卡记录并合并"""
        bill_id = (params or {}).get('bill_id')
        if not bill_id:
            return self.err('缺少账单ID')

        from modules.accounting.cross_platform_merger import CrossPlatformMerger
        merger = CrossPlatformMerger(self.dal)

        # 获取孤儿记录的完整信息
        bill = self.dal.fetch_one(
            "SELECT ub.*, ba.merge_status FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.id = ? AND ba.merge_status = 'orphan'",
            (bill_id,)
        )
        if not bill:
            return self.ok({'merged': False, 'message': '未找到孤儿记录'})

        # 尝试查找匹配的银行卡记录并合并
        result = merger.mark_orphan(dict(bill))
        if result.get('merged'):
            return self.ok({'merged': True, 'merged_group_id': result.get('merged_group_id')})
        return self.ok({'merged': False, 'message': '未找到匹配的银行卡记录'})

    def get_weak_match_candidates(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        from modules.accounting.transfer_pairer import TransferPairer
        pairer = TransferPairer(self.dal)
        bill = self.dal.fetch_one(
            "SELECT * FROM unified_bills WHERE id = ?", (bill_id,)
        )
        if not bill:
            return self.err('账单不存在')
        candidates = pairer.auto_pair_weak_candidates(dict(bill))
        return self.ok({'candidates': candidates})

    def get_transfer_strong_pairs(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT ba.transfer_link_id, "
            "out_b.id AS out_bill_id, out_b.trade_time AS out_trade_time, out_b.amount_cents AS out_amount_cents, "
            "out_b.counterparty AS out_counterparty, out_b.channel AS out_channel, out_b.remark AS out_remark, "
            "in_b.id AS in_bill_id, in_b.trade_time AS in_trade_time, in_b.amount_cents AS in_amount_cents, "
            "in_b.counterparty AS in_counterparty, in_b.channel AS in_channel, in_b.remark AS in_remark "
            "FROM bill_accounting ba "
            "JOIN unified_bills out_b ON ba.bill_id = out_b.id AND out_b.direction = 'expense' "
            "JOIN bill_accounting ba2 ON ba.transfer_link_id = ba2.transfer_link_id "
            "JOIN unified_bills in_b ON ba2.bill_id = in_b.id AND in_b.direction = 'income' "
            "WHERE ba.transfer_link_id IS NOT NULL AND ba.transfer_link_id != '' "
            "AND out_b.trade_type = 'transfer_out' "
            "AND in_b.trade_type = 'transfer_in' "
            "GROUP BY ba.transfer_link_id "
            "ORDER BY out_b.trade_time DESC"
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def get_transfer_weak_candidates(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT ub.* FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.trade_type = 'transfer_out' AND ub.is_deleted = 0 "
            "AND (ba.transfer_link_id IS NULL OR ba.transfer_link_id = '') "
            "ORDER BY ub.trade_time DESC"
        )
        from modules.accounting.transfer_pairer import TransferPairer
        pairer = TransferPairer(self.dal)
        candidates = []
        for row in rows:
            candidates.extend(pairer.auto_pair_weak_candidates(dict(row)))
        return self.ok({'list': candidates, 'total': len(candidates)})

    def confirm_transfer_pair(self, params=None) -> dict:
        p = params or {}
        out_id = p.get('out_id')
        in_id = p.get('in_id')
        if not out_id or not in_id:
            return self.err('缺少配对账单')
        from modules.accounting.transfer_pairer import TransferPairer
        pairer = TransferPairer(self.dal)
        result = pairer.confirm_pair(out_id, in_id)
        return self.ok(result)

    def reject_transfer_pair(self, params=None) -> dict:
        p = params or {}
        out_id = p.get('out_id')
        in_id = p.get('in_id')
        if not out_id or not in_id:
            return self.err('缺少配对账单')
        from modules.accounting.transfer_pairer import TransferPairer
        pairer = TransferPairer(self.dal)
        return self.ok(pairer.reject_pair(out_id, in_id))

    def get_credit_accounts(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT ca.*, r.name AS role_name, a.account_name AS linked_account_name "
            "FROM credit_accounts ca "
            "LEFT JOIN roles r ON ca.role_id = r.id "
            "LEFT JOIN accounts a ON ca.linked_account_id = a.id "
            "ORDER BY ca.id DESC"
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def create_credit_account(self, params=None) -> dict:
        p = params or {}
        account_name = (p.get('account_name') or '').strip()
        credit_type = (p.get('credit_type') or '').strip()
        role_id = p.get('role_id')
        if not account_name or not credit_type:
            return self.err('请填写账户名称和信用类型')
        if not role_id:
            return self.err('请选择归属角色')
        credit_account_id = self.dal.insert('credit_accounts', {
            'account_name': account_name,
            'credit_type': credit_type,
            'role_id': role_id,
            'linked_account_id': p.get('linked_account_id'),
            'credit_limit_cents': p.get('credit_limit_cents', 0) or 0,
        })
        return self.ok({'credit_account_id': credit_account_id})

    def update_credit_account(self, params=None) -> dict:
        p = params or {}
        credit_account_id = p.get('credit_account_id')
        current = self.dal.fetch_one("SELECT id FROM credit_accounts WHERE id = ?", (credit_account_id,))
        if not current:
            return self.err('信用账户不存在')
        data = {}
        for key in ('account_name', 'credit_type', 'role_id', 'linked_account_id', 'credit_limit_cents'):
            if key in p:
                data[key] = p.get(key)
        if not data:
            return self.ok()
        self.dal.update('credit_accounts', data, 'id = ?', (credit_account_id,))
        return self.ok()

    def delete_credit_account(self, params=None) -> dict:
        credit_account_id = (params or {}).get('credit_account_id')
        ref = self.dal.fetch_one(
            "SELECT id FROM bill_accounting WHERE credit_account_id = ? LIMIT 1", (credit_account_id,)
        )
        if ref:
            return self.err('信用账户已被账务记录引用，不能删除')
        deleted = self.dal.delete('credit_accounts', 'id = ?', (credit_account_id,))
        return self.ok() if deleted else self.err('信用账户不存在')

    def get_credit_records(self, params=None) -> dict:
        p = params or {}
        rows = self._query_credit_like_records('credit_consumption', p)
        return self.ok({'list': rows})

    def get_repayment_records(self, params=None) -> dict:
        p = params or {}
        rows = self._query_credit_like_records('repayment', p)
        return self.ok({'list': rows})

    def toggle_hide_repayment_transfer(self, params=None) -> dict:
        hide = (params or {}).get('hide', False)
        return self.ok({'hide': hide})

    # ─── 6.2.6 统计报表 ────────────────────────────

    def _query_credit_like_records(self, trade_type: str, params=None) -> list[dict]:
        p = params or {}
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        conditions = ["ub.is_deleted = 0", "ub.trade_type = ?"]
        sql_params = [trade_type]
        if month:
            year, month_num = [int(v) for v in str(month).split('-')]
            start = f"{year}-{month_num:02d}-01T00:00:00+08:00"
            if month_num == 12:
                end = f"{year + 1}-01-01T00:00:00+08:00"
            else:
                end = f"{year}-{month_num + 1:02d}-01T00:00:00+08:00"
            conditions.extend(["ub.trade_time >= ?", "ub.trade_time < ?"])
            sql_params.extend([start, end])
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)
        where = " AND ".join(conditions)
        rows = self.dal.fetch_all(
            "SELECT ub.*, ba.transfer_link_id, ba.is_credit, ba.credit_account_id, "
            "ca.account_name AS credit_account_name, a.account_name AS linked_account_name "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "LEFT JOIN credit_accounts ca ON ba.credit_account_id = ca.id "
            "LEFT JOIN accounts a ON ca.linked_account_id = a.id "
            f"WHERE {where} ORDER BY ub.trade_time DESC",
            tuple(sql_params),
        )
        return [dict(r) for r in rows]

    def _append_report_scope_filters(self, conditions: list, sql_params: list, family_id=None, role_id=None) -> None:
        if family_id:
            conditions.append(
                "EXISTS (SELECT 1 FROM role_families rf WHERE rf.role_id = ub.role_id AND rf.family_id = ?)"
            )
            sql_params.append(family_id)
        if role_id:
            conditions.append("ub.role_id = ?")
            sql_params.append(role_id)

    def _append_internal_flow_filters(self, conditions: list, hide_internal: bool) -> None:
        if hide_internal:
            conditions.append(
                "ub.trade_type NOT IN ('transfer_out', 'transfer_in', 'repayment', 'repayment_mirror')"
            )

    def get_monthly_summary(self, params=None) -> dict:
        p = params or {}
        year = p.get('year')
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))
        start = f"{year}-{month:02d}-01T00:00:00+08:00"
        if month == 12:
            end = f"{year + 1}-01-01T00:00:00+08:00"
        else:
            end = f"{year}-{month + 1:02d}-01T00:00:00+08:00"

        base_query = "FROM unified_bills ub"
        conditions = ["ub.is_deleted = 0", "ub.trade_time >= ?", "ub.trade_time < ?"]
        sql_params = [start, end]
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)

        where = " AND ".join(conditions)
        scoped_conditions = list(conditions)
        self._append_internal_flow_filters(scoped_conditions, hide_internal)
        scoped_where = " AND ".join(scoped_conditions)

        income = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {scoped_where} AND ub.direction = 'income'",
            tuple(sql_params),
        )['total']

        expense = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {scoped_where} AND ub.direction = 'expense' AND ub.trade_type != 'credit_consumption'",
            tuple(sql_params),
        )['total']

        credit = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {where} AND ub.trade_type = 'credit_consumption'",
            tuple(sql_params),
        )['total']

        repayment = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {where} AND ub.trade_type = 'repayment'",
            tuple(sql_params),
        )['total']

        return self.ok({
            'income': income,
            'expense': expense,
            'credit': credit,
            'repayment': repayment,
        })

    def get_category_distribution(self, params=None) -> dict:
        p = params or {}
        year = p.get('year')
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        direction = p.get('direction', 'expense')
        hide_internal = bool(p.get('hide_internal', False))
        start = f"{year}-{month:02d}-01T00:00:00+08:00"
        if month == 12:
            end = f"{year + 1}-01-01T00:00:00+08:00"
        else:
            end = f"{year}-{month + 1:02d}-01T00:00:00+08:00"

        conditions = [
            "ub.is_deleted = 0", "ub.trade_time >= ?", "ub.trade_time < ?",
            "ub.direction = ?",
        ]
        sql_params = [start, end, direction]
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)
        self._append_internal_flow_filters(conditions, hide_internal)

        where = " AND ".join(conditions)

        rows = self.dal.fetch_all(
            f"SELECT bc.name as category_name, bc.icon, "
            f"SUM(ub.amount_cents) as total_amount, COUNT(*) as count "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_categories bc ON ub.category_id = bc.id "
            f"WHERE {where} "
            f"GROUP BY ub.category_id ORDER BY total_amount DESC",
            tuple(sql_params),
        )

        return self.ok({'categories': [dict(r) for r in rows]})

    def get_trend_data(self, params=None) -> dict:
        p = params or {}
        start_month = p.get('start_month')
        end_month = p.get('end_month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))
        months = []
        income_list = []
        expense_list = []

        start_dt = datetime.strptime(start_month, '%Y-%m')
        end_dt = datetime.strptime(end_month, '%Y-%m')
        current = start_dt

        while current <= end_dt:
            month_str = current.strftime('%Y-%m')
            months.append(month_str)

            summary = self.get_monthly_summary({
                'year': current.year,
                'month': current.month,
                'family_id': family_id,
                'role_id': role_id,
                'hide_internal': hide_internal,
            })
            data = summary.get('data', {})
            income_list.append(data.get('income', 0))
            expense_list.append(data.get('expense', 0))

            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return self.ok({
            'months': months,
            'income': income_list,
            'expense': expense_list,
        })

    # ─── 6.2.7 系统设置 ────────────────────────────

    def get_families(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT f.*, "
            "(SELECT COUNT(DISTINCT rf.role_id) FROM role_families rf "
            " WHERE rf.family_id = f.id) as role_count "
            "FROM families f ORDER BY f.id"
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def create_family(self, params=None) -> dict:
        name = (params or {}).get('name', '')
        fid = self.dal.insert('families', {'name': name})
        return self.ok({'family_id': fid})

    def update_family(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        name = p.get('name')
        is_default = p.get('is_default')
        data = {}
        if name is not None:
            data['name'] = name
        try:
            with self.dal.transaction():
                if is_default is not None:
                    if is_default:
                        self.dal.execute("UPDATE families SET is_default = 0")
                    data['is_default'] = is_default
                self.dal.update('families', data, 'id = ?', (family_id,))
            return self.ok()
        except Exception as e:
            return self.err(f'更新家庭失败: {e}')

    def delete_family(self, params=None) -> dict:
        family_id = (params or {}).get('family_id')
        self.dal.delete('families', 'id = ?', (family_id,))
        return self.ok()

    def get_roles(self, params=None) -> dict:
        family_id = (params or {}).get('family_id')
        if family_id:
            rows = self.dal.fetch_all(
                "SELECT r.* FROM roles r "
                "JOIN role_families rf ON r.id = rf.role_id "
                "WHERE rf.family_id = ?", (family_id,))
        else:
            rows = self.dal.fetch_all("SELECT * FROM roles")
        return self.ok({'list': [dict(r) for r in rows]})

    def create_role(self, params=None) -> dict:
        p = params or {}
        name = p.get('name', '')
        family_id = p.get('family_id')
        role_type = p.get('role_type', 'personal')
        try:
            with self.dal.transaction():
                rid = self.dal.insert('roles', {
                    'name': name, 'role_type': role_type,
                })
                if family_id:
                    self.dal.insert('role_families', {
                        'role_id': rid, 'family_id': family_id,
                    })
            return self.ok({'role_id': rid})
        except Exception as e:
            return self.err(f'创建角色失败: {e}')

    def update_role(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        name = p.get('name')
        role_type = p.get('role_type')
        data = {}
        if name is not None:
            data['name'] = name
        if role_type is not None:
            data['role_type'] = role_type
        self.dal.update('roles', data, 'id = ?', (role_id,))
        return self.ok()

    def delete_role(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        self.dal.delete('roles', 'id = ?', (role_id,))
        return self.ok()

    def get_accounts(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        base_sql = (
            "SELECT a.*, r.name AS role_name, "
            "target.account_name AS canonical_account_name, "
            "target.id AS canonical_account_id, "
            "(SELECT COUNT(1) FROM account_aliases aa WHERE aa.account_id = a.id) AS alias_count "
            "FROM accounts a "
            "LEFT JOIN roles r ON a.role_id = r.id "
            "LEFT JOIN accounts target ON a.merged_into_account_id = target.id"
        )
        if role_id:
            rows = self.dal.fetch_all(
                f"{base_sql} WHERE a.role_id = ? ORDER BY a.id DESC", (role_id,)
            )
        else:
            rows = self.dal.fetch_all(f"{base_sql} ORDER BY a.id DESC")
        return self.ok({'list': [dict(r) for r in rows]})

    def _sync_account_bills_role(self, account_id: int, role_id, snapshot_type='account_role_change') -> int:
        bills = self.dal.fetch_all(
            "SELECT id FROM unified_bills WHERE account_id = ? AND is_deleted = 0",
            (account_id,),
        )
        bill_ids = [b['id'] for b in bills]
        if not bill_ids:
            return 0

        snapshot_id = self.snapshot.create_snapshot(
            snapshot_type,
            f'账户{account_id}角色变更，级联更新{len(bill_ids)}条账单',
            bill_ids,
        )

        new_assign_status = 'assigned' if role_id else 'pending'
        placeholders = ', '.join(['?' for _ in bill_ids])
        self.dal.execute(
            f"UPDATE unified_bills SET role_id = ?, assign_status = ?, updated_at = ? WHERE id IN ({placeholders})",
            (role_id, new_assign_status, self._now(), *bill_ids),
        )
        self.snapshot.finalize_snapshot(snapshot_id, bill_ids)
        return len(bill_ids)

    def get_account_aliases(self, params=None) -> dict:
        account_id = (params or {}).get('account_id')
        account = self.dal.fetch_one("SELECT id, channel FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.ok({'list': []})
        rows = self.dal.fetch_all(
            "SELECT * FROM account_aliases WHERE account_id = ? ORDER BY id DESC",
            (account_id,),
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def create_account_alias(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        alias_value = str(p.get('alias_value', '')).strip()
        alias_type = p.get('alias_type', 'wechat_nickname')
        account = self.dal.fetch_one("SELECT id, channel FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.err('当前仅支持维护微信账户曾用名')
        if not alias_value:
            return self.err('请输入曾用名')
        try:
            self.dal.insert_or_ignore('account_aliases', {
                'account_id': account_id,
                'channel': 'wechat',
                'alias_type': alias_type,
                'alias_value': alias_value,
                'source_kind': 'manual',
                'created_at': self._now(),
            })
            return self.ok()
        except Exception as e:
            return self.err(f'保存曾用名失败: {e}')

    def delete_account_alias(self, params=None) -> dict:
        alias_id = (params or {}).get('alias_id')
        deleted = self.dal.delete('account_aliases', 'id = ?', (alias_id,))
        return self.ok() if deleted else self.err('曾用名不存在')

    def merge_wechat_accounts(self, params=None) -> dict:
        p = params or {}
        source_id = p.get('source_account_id')
        target_id = p.get('target_account_id')
        if not source_id or not target_id or source_id == target_id:
            return self.err('请选择不同的源账户和目标账户')

        source = self.dal.fetch_one("SELECT * FROM accounts WHERE id = ?", (source_id,))
        target = self.dal.fetch_one("SELECT * FROM accounts WHERE id = ?", (target_id,))
        if not source or not target:
            return self.err('账户不存在')
        if source['channel'] != 'wechat' or target['channel'] != 'wechat':
            return self.err('当前仅支持合并微信账户')

        canonical_target_id = self._resolve_canonical_account_id(target_id)
        if canonical_target_id == source_id:
            return self.err('不能合并到自身或其下级账户')

        try:
            merge_session_id = str(uuid.uuid4())
            with self.dal.transaction():
                self.dal.update(
                    'accounts',
                    {'merged_into_account_id': canonical_target_id},
                    'id = ?',
                    (source_id,),
                )
                # 把源账户展示名中可识别的微信昵称沉淀为目标账户别名，减少后续导入裂变。
                self._add_wechat_alias(
                    canonical_target_id,
                    source['account_name'].replace('微信-', '').split('-')[0],
                    source_kind='merge_auto_added',
                    source_account_id=source_id,
                    merge_session_id=merge_session_id,
                )
            self._account_cache.clear()
            return self.ok({
                'source_account_id': source_id,
                'target_account_id': canonical_target_id,
                'merge_session_id': merge_session_id,
            })
        except Exception as e:
            return self.err(f'合并微信账户失败: {e}')

    def _retrace_related_real_payer_bills(self, account_ids: list[int]) -> dict:
        """局部重跑与指定账户相关的真实支付者溯源。"""
        account_ids = [aid for aid in account_ids if aid]
        if not account_ids:
            return {'groups_undone': 0, 'bills_retraced': 0, 'merged_count': 0}

        placeholders = ', '.join(['?' for _ in account_ids])
        affected_rows = self.dal.fetch_all(
            f"SELECT ub.id, ub.channel, ba.merged_group_id "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"WHERE ub.is_deleted = 0 AND (ub.account_id IN ({placeholders}) "
            f"OR ba.real_payer_account_id IN ({placeholders}))",
            tuple(account_ids) + tuple(account_ids),
        )
        group_ids = sorted({r['merged_group_id'] for r in affected_rows if r.get('merged_group_id')})
        bill_ids = {r['id'] for r in affected_rows}

        from modules.accounting.cross_platform_merger import CrossPlatformMerger
        merger = CrossPlatformMerger(self.dal)

        for group_id in group_ids:
            members = merger.get_merged_group(group_id)
            bill_ids.update(m['id'] for m in members)
            merger.undo_merge(group_id)

        orphan_rows = self.dal.fetch_all(
            f"SELECT ub.id FROM unified_bills ub "
            f"JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"WHERE ub.is_deleted = 0 AND ba.merge_status = 'orphan' "
            f"AND ub.account_id IN ({placeholders})",
            tuple(account_ids),
        )
        bill_ids.update(r['id'] for r in orphan_rows)

        bills = self.dal.fetch_all(
            f"SELECT * FROM unified_bills WHERE id IN ({', '.join(['?' for _ in bill_ids])}) AND is_deleted = 0 "
            f"ORDER BY trade_time ASC" if bill_ids else "SELECT * FROM unified_bills WHERE 1 = 0",
            tuple(bill_ids),
        )

        merged_count = 0
        retraced_count = 0
        for bill in bills:
            bill_dict = dict(bill)
            result = None
            if bill['channel'] in ('wechat', 'alipay'):
                result = merger.mark_orphan(bill_dict)
                retraced_count += 1
            elif bill['channel'] == 'ccb':
                result = merger.try_merge(bill_dict)
                retraced_count += 1
            if result and result.get('merged'):
                merged_count += 1

        return {
            'groups_undone': len(group_ids),
            'bills_retraced': retraced_count,
            'merged_count': merged_count,
        }

    def unmerge_wechat_account(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        remove_auto_added_target_aliases = bool(p.get('remove_auto_added_target_aliases', False))
        return_source_aliases = bool(p.get('return_source_aliases', False))
        retrace_related_bills = bool(p.get('retrace_related_bills', False))

        account = self.dal.fetch_one("SELECT id, channel, merged_into_account_id FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.err('当前仅支持微信账户取消合并')

        target_id = account.get('merged_into_account_id')
        result = {
            'detached': False,
            'removed_alias_count': 0,
            'returned_alias_count': 0,
            'retrace': None,
        }

        try:
            with self.dal.transaction():
                self.dal.update('accounts', {'merged_into_account_id': None}, 'id = ?', (account_id,))
                result['detached'] = True

                if remove_auto_added_target_aliases and target_id:
                    result['removed_alias_count'] = self.dal.delete(
                        'account_aliases',
                        "account_id = ? AND source_account_id = ? AND source_kind = ?",
                        (target_id, account_id, 'merge_auto_added'),
                    )

                if return_source_aliases and target_id:
                    result['returned_alias_count'] = self.dal.update(
                        'account_aliases',
                        {
                            'account_id': account_id,
                            'source_kind': 'manual',
                            'source_account_id': None,
                            'merge_session_id': None,
                        },
                        "account_id = ? AND source_account_id = ? AND source_kind = ?",
                        (target_id, account_id, 'merge_reassigned'),
                    )

            if retrace_related_bills:
                related_ids = [account_id]
                if target_id:
                    related_ids.append(target_id)
                result['retrace'] = self._retrace_related_real_payer_bills(related_ids)

            self._account_cache.clear()
            return self.ok(result)
        except Exception as e:
            return self.err(f'取消合并失败: {e}')

    def create_account(self, params=None) -> dict:
        p = params or {}
        account_name = p.get('account_name', '')
        account_tag = p.get('account_tag', '')
        channel = p.get('channel', '')
        role_id = p.get('role_id')
        aid = self.dal.insert('accounts', {
            'account_name': account_name,
            'account_tag': account_tag,
            'channel': channel,
            'role_id': role_id,
        })
        return self.ok({'account_id': aid})

    def update_account(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        data = {k: v for k, v in p.items()
                if k in ('account_name', 'account_tag', 'channel', 'role_id')}

        try:
            with self.dal.transaction():
                if 'role_id' in data:
                    old_account = self.dal.fetch_one(
                        "SELECT role_id FROM accounts WHERE id = ?", (account_id,)
                    )
                    if old_account and old_account['role_id'] != data['role_id']:
                        self._sync_account_bills_role(account_id, data['role_id'])

                self.dal.update('accounts', data, 'id = ?', (account_id,))
            return self.ok()
        except Exception as e:
            return self.err(f'更新账户失败: {e}')

    def batch_assign_account_role(self, params=None) -> dict:
        p = params or {}
        account_ids = p.get('account_ids', [])
        role_id = p.get('role_id')
        if not account_ids:
            return self.err('未选择账户')
        if not role_id:
            return self.err('未选择目标角色')

        role = self.dal.fetch_one("SELECT id FROM roles WHERE id = ?", (role_id,))
        if not role:
            return self.err('目标角色不存在')

        placeholders = ', '.join(['?' for _ in account_ids])
        rows = self.dal.fetch_all(
            f"SELECT id, role_id FROM accounts WHERE id IN ({placeholders})",
            tuple(account_ids),
        )
        if len(rows) != len(account_ids):
            return self.err('部分账户不存在')

        updated_ids = []
        try:
            with self.dal.transaction():
                for row in rows:
                    account_id = row['id']
                    if row['role_id'] == role_id:
                        continue
                    self._sync_account_bills_role(account_id, role_id, 'batch_account_role_change')
                    self.dal.update('accounts', {'role_id': role_id}, 'id = ?', (account_id,))
                    updated_ids.append(account_id)
            return self.ok({'updated_count': len(updated_ids)})
        except Exception as e:
            return self.err(f'批量分配角色失败: {e}')

    def delete_account(self, params=None) -> dict:
        account_id = (params or {}).get('account_id')
        refs = [
            self.dal.fetch_one("SELECT id FROM unified_bills WHERE account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM bill_accounting WHERE real_payer_account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM credit_accounts WHERE linked_account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM accounts WHERE merged_into_account_id = ? LIMIT 1", (account_id,)),
        ]
        if any(refs):
            return self.err('账户已被账单、真实支付者或合并关系引用，不能直接删除')
        with self.dal.transaction():
            self.dal.delete('account_aliases', 'account_id = ?', (account_id,))
            deleted = self.dal.delete('accounts', 'id = ?', (account_id,))
        return self.ok() if deleted else self.err('账户不存在')

    def get_categories(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT * FROM bill_categories ORDER BY level, parent_id, sort_order, id")
        return self.ok({'list': [dict(r) for r in rows]})

    def create_category(self, params=None) -> dict:
        p = params or {}
        name = p.get('name', '')
        icon = p.get('icon', '')
        parent_id = p.get('parent_id')
        level = 1
        if parent_id:
            parent = self.dal.fetch_one("SELECT id, level FROM bill_categories WHERE id = ?", (parent_id,))
            if not parent:
                return self.err('父分类不存在')
            if parent['level'] != 1:
                return self.err('仅支持两级分类')
            level = 2
        cid = self.dal.insert('bill_categories', {
            'name': name,
            'icon': icon,
            'parent_id': parent_id,
            'level': level,
            'sort_order': p.get('sort_order', 0),
            'source': 'user',
            'is_enabled': p.get('is_enabled', 1),
            'created_at': self._now(),
            'updated_at': self._now(),
        })
        return self.ok({'category_id': cid})

    def update_category(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        current = self.dal.fetch_one("SELECT * FROM bill_categories WHERE id = ?", (category_id,))
        if not current:
            return self.err('分类不存在')
        data = {}
        for key in ('name', 'icon', 'sort_order', 'is_enabled'):
            if p.get(key) is not None:
                data[key] = p.get(key)
        if 'parent_id' in p:
            parent_id = p.get('parent_id')
            if parent_id == category_id:
                return self.err('不能选择自身作为父分类')
            level = 1
            if parent_id:
                parent = self.dal.fetch_one("SELECT id, level FROM bill_categories WHERE id = ?", (parent_id,))
                if not parent:
                    return self.err('父分类不存在')
                if parent['level'] != 1:
                    return self.err('仅支持两级分类')
                child = self.dal.fetch_one("SELECT id FROM bill_categories WHERE parent_id = ? LIMIT 1", (category_id,))
                if child:
                    return self.err('已有子分类的一级分类不能改为二级分类')
                level = 2
            data['parent_id'] = parent_id
            data['level'] = level
        if not data:
            return self.ok()
        data['updated_at'] = self._now()
        self.dal.update('bill_categories', data, 'id = ?', (category_id,))
        return self.ok()

    def delete_category(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        category = self.dal.fetch_one("SELECT * FROM bill_categories WHERE id = ?", (category_id,))
        if not category:
            return self.err('分类不存在')
        if category.get('source') == 'system':
            return self.err('系统分类不能删除，可选择禁用')
        refs = [
            self.dal.fetch_one("SELECT id FROM bill_categories WHERE parent_id = ? LIMIT 1", (category_id,)),
            self.dal.fetch_one("SELECT id FROM category_keywords WHERE category_id = ? LIMIT 1", (category_id,)),
            self.dal.fetch_one("SELECT id FROM unified_bills WHERE category_id = ? LIMIT 1", (category_id,)),
        ]
        if any(refs):
            return self.err('分类已被子分类、规则或账单引用，不能删除')
        self.dal.delete('bill_categories', 'id = ?', (category_id,))
        return self.ok()

    def get_category_match_fields(self, params=None) -> dict:
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        return self.ok({'list': service.list_match_fields()})

    def get_category_keywords(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        rows = self.dal.fetch_all(
            "SELECT * FROM category_keywords WHERE category_id = ? ORDER BY priority DESC, weight DESC, id ASC",
            (category_id,))
        result = []
        for row in rows:
            item = dict(row)
            item['match_field'] = service.normalize_match_field(item.get('match_field') or 'counterparty')
            result.append(item)
        return self.ok({'list': result})

    def save_category_keywords(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        keywords = p.get('keywords', [])
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        try:
            with self.dal.transaction():
                self.dal.delete('category_keywords', 'category_id = ?', (category_id,))
                for kw in keywords:
                    keyword = str(kw.get('keyword', '')).strip()
                    if not keyword:
                        continue
                    match_field = service.normalize_match_field(kw.get('match_field', 'counterparty'))
                    self.dal.insert('category_keywords', {
                        'category_id': category_id,
                        'keyword': keyword,
                        'match_field': match_field,
                        'weight': kw.get('weight', 10),
                        'priority': kw.get('priority', 0),
                        'match_mode': kw.get('match_mode', 'contains'),
                        'is_enabled': kw.get('is_enabled', 1),
                        'source': kw.get('source', 'user'),
                        'created_at': self._now(),
                        'updated_at': self._now(),
                    })
            return self.ok()
        except Exception as e:
            return self.err(f'保存关键词失败: {e}')

    # ─── 6.2.8 数据管理 ────────────────────────────

    def reparse(self, params=None) -> dict:
        scope = (params or {}).get('scope')
        from modules.reparser.reparser import ReParser
        rp = ReParser(self.db, self.config)
        result = rp.reparse(scope)
        if result.get('success'):
            return self.ok(result)
        return self.err(result.get('message', '重新解析失败'))

    def recategorize_bills(self, params=None) -> dict:
        p = params or {}
        from modules.categorizer import CategoryReclassifier
        reclassifier = CategoryReclassifier(self.dal, self.snapshot)
        try:
            result = reclassifier.recategorize(
                p.get('scope') or {'type': 'all'},
                only_uncategorized=p.get('only_uncategorized', False),
                include_income=p.get('include_income', False),
            )
            return self.ok(result)
        except Exception as e:
            return self.err(f'重新分类失败: {e}')

    def recategorize_bill(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        if not bill_id:
            return self.err('未指定账单')
        from modules.categorizer import CategoryReclassifier
        reclassifier = CategoryReclassifier(self.dal, self.snapshot)
        try:
            result = reclassifier.recategorize({'type': 'bill_ids', 'bill_ids': [bill_id]})
            return self.ok(result)
        except Exception as e:
            return self.err(f'重新分类失败: {e}')

    def list_snapshots(self, params=None) -> dict:
        limit = (params or {}).get('limit', 20)
        snapshots = self.snapshot.list_snapshots(limit)
        return self.ok({'list': snapshots})

    def get_snapshot_details(self, params=None) -> dict:
        snapshot_id = (params or {}).get('snapshot_id')
        details = self.snapshot.get_snapshot_details(snapshot_id)
        return self.ok({'details': details})

    def restore_snapshot(self, params=None) -> dict:
        snapshot_id = (params or {}).get('snapshot_id')
        result = self.snapshot.restore_snapshot(snapshot_id)
        if result.get('success'):
            return self.ok(result)
        return self.err(result.get('message', '回退失败'))

    def delete_snapshot(self, params=None) -> dict:
        snapshot_id = (params or {}).get('snapshot_id')
        success = self.snapshot.delete_snapshot(snapshot_id)
        return self.ok() if success else self.err('删除失败')

    def cleanup_source_bills(self, params=None) -> dict:
        before_date = (params or {}).get('before_date')
        deleted = self.dal.delete(
            'source_bills',
            "created_at < ? AND bill_id IN (SELECT id FROM unified_bills WHERE is_deleted = 1)",
            (before_date,),
        )
        return self.ok({'deleted_count': deleted})

    def cleanup_snapshots(self, params=None) -> dict:
        keep_count = (params or {}).get('keep_count', 50)
        deleted = self.snapshot.cleanup_old_snapshots(keep_count)
        return self.ok({'deleted_count': deleted})

    def reset_application(self, params=None) -> dict:
        p = params or {}
        if p.get('confirm_text') != 'RESET':
            return self.err('确认文本不正确')

        backup = p.get('backup', True)
        db_path = self.db.db_path
        try:
            with self.db._lock:
                self.db.close()
                result = rebuild_database(db_path, backup=backup)
                self.db.initialize()
                self.dal = DAL(self.db)
                self.snapshot = SnapshotEngine(self.db, dal=self.dal)
                self._account_cache.clear()
                self._default_ids = None
            return self.ok({
                'message': '应用已重置',
                'db_path': result.get('db_path'),
                'backup_path': result.get('backup_path'),
            })
        except Exception as e:
            try:
                self.db.initialize()
                self.dal = DAL(self.db)
                self.snapshot = SnapshotEngine(self.db, dal=self.dal)
            except Exception:
                logger.exception("failed to reinitialize database after reset failure")
            return self.err(f'重置失败: {e}')

    # ─── 6.2.9 账单删除 ────────────────────────────

    def clear_all_bills(self, params=None) -> dict:
        try:
            with self.dal.transaction():
                # 先收集所有账单ID并处理合并组级联
                all_bills = self.dal.fetch_all("SELECT id FROM unified_bills")
                all_bill_ids = [b['id'] for b in all_bills]
                if all_bill_ids:
                    self._handle_merge_group_cascade(all_bill_ids)
                self.dal.execute("DELETE FROM bill_accounting")
                self.dal.execute("DELETE FROM source_bills")
                self.dal.execute("DELETE FROM unified_bills")
                self.dal.execute("DELETE FROM import_batches")
                self.dal.execute(
                    "UPDATE collection_records SET status = 'pending', batch_id = NULL, parse_result = NULL"
                )
            return self.ok({'message': '所有账单数据已清除'})
        except Exception as e:
            return self.err(f'清除失败: {e}')

    def clear_bills_by_collection(self, params=None) -> dict:
        record_ids = (params or {}).get('record_ids', [])
        if not record_ids:
            return self.err('未指定采集记录')

        try:
            total_deleted = 0
            with self.dal.transaction():
                # 先收集所有涉及的账单ID，统一处理合并组级联
                all_bill_ids = []
                for record_id in record_ids:
                    record = self.dal.fetch_one(
                        "SELECT batch_id FROM collection_records WHERE id = ?", (record_id,)
                    )
                    if record and record['batch_id']:
                        bills = self.dal.fetch_all(
                            "SELECT id FROM unified_bills WHERE batch_id = ?", (record['batch_id'],)
                        )
                        all_bill_ids.extend([b['id'] for b in bills])

                if all_bill_ids:
                    self._handle_merge_group_cascade(all_bill_ids)

                for record_id in record_ids:
                    record = self.dal.fetch_one(
                        "SELECT batch_id FROM collection_records WHERE id = ?", (record_id,)
                    )
                    if not record or not record['batch_id']:
                        continue

                    batch_id = record['batch_id']

                    bills = self.dal.fetch_all(
                        "SELECT id FROM unified_bills WHERE batch_id = ?", (batch_id,)
                    )
                    bill_ids = [b['id'] for b in bills]

                    if bill_ids:
                        placeholders = ', '.join(['?' for _ in bill_ids])
                        self.dal.execute(
                            f"DELETE FROM bill_accounting WHERE bill_id IN ({placeholders})",
                            tuple(bill_ids)
                        )
                        self.dal.execute(
                            f"DELETE FROM source_bills WHERE bill_id IN ({placeholders})",
                            tuple(bill_ids)
                        )
                        self.dal.execute(
                            f"DELETE FROM unified_bills WHERE batch_id = ?", (batch_id,)
                        )
                        total_deleted += len(bill_ids)

                    self.dal.execute(
                        "DELETE FROM import_batches WHERE batch_id = ?", (batch_id,)
                    )

                    self.dal.update(
                        'collection_records',
                        {'status': 'pending', 'batch_id': None, 'parse_result': None},
                        'id = ?',
                        (record_id,),
                    )

            return self.ok({'deleted_count': total_deleted})
        except Exception as e:
            return self.err(f'清除失败: {e}')

    # ─── 合并组级联处理（内部辅助） ────────────────────────────

    def _handle_merge_group_cascade(self, bill_ids: list) -> None:
        """
        删除账单前处理合并组内剩余记录的级联恢复。

        规则：
        - 删除 merged_source（微信/支付宝发起方）→ merged_target 恢复为 normal + 还原 original_* 字段
        - 删除 merged_target（银行卡真实支付者）→ merged_source 恢复为 orphan
        - 合并组内全部被删 → 无需额外处理（调用方负责删除 bill_accounting）
        """
        if not bill_ids:
            return

        placeholders = ', '.join(['?' for _ in bill_ids])
        params = tuple(bill_ids)

        groups = self.dal.fetch_all(
            f"SELECT DISTINCT merged_group_id FROM bill_accounting "
            f"WHERE bill_id IN ({placeholders}) AND merged_group_id IS NOT NULL",
            params
        )

        if not groups:
            return

        deleted_set = set(bill_ids)

        for g in groups:
            gid = g['merged_group_id']
            members = self.dal.fetch_all(
                "SELECT bill_id, merge_status, original_counterparty, original_product_desc "
                "FROM bill_accounting WHERE merged_group_id = ?",
                (gid,)
            )

            remaining = [m for m in members if m['bill_id'] not in deleted_set]
            deleted_in_group = [m for m in members if m['bill_id'] in deleted_set]

            if not remaining:
                continue

            has_deleted_source = any(
                m['merge_status'] == 'merged_source' for m in deleted_in_group
            )
            has_deleted_target = any(
                m['merge_status'] == 'merged_target' for m in deleted_in_group
            )

            for r in remaining:
                if r['merge_status'] == 'merged_target' and has_deleted_source:
                    # 发起方被删 → 真实支付者恢复为 normal，还原原始字段
                    restore = {}
                    if r.get('original_counterparty') is not None:
                        restore['counterparty'] = r['original_counterparty']
                    if r.get('original_product_desc') is not None:
                        restore['product_desc'] = r['original_product_desc']
                    if restore:
                        self.dal.update(
                            'unified_bills', restore, 'id = ?', (r['bill_id'],)
                        )
                    self.dal.update(
                        'bill_accounting',
                        {
                            'merge_status': 'normal',
                            'merged_group_id': None,
                            'real_payer_account_id': None,
                            'original_counterparty': None,
                            'original_product_desc': None,
                        },
                        'bill_id = ?',
                        (r['bill_id'],),
                    )

                elif r['merge_status'] == 'merged_source' and has_deleted_target:
                    # 真实支付者被删 → 发起方恢复为 orphan
                    self.dal.update(
                        'bill_accounting',
                        {
                            'merge_status': 'orphan',
                            'merged_group_id': None,
                            'real_payer_account_id': None,
                            'original_counterparty': None,
                            'original_product_desc': None,
                        },
                        'bill_id = ?',
                        (r['bill_id'],),
                    )

    # ─── 6.2.8 删除/回收站 ────────────────────────────────────

    def delete_bill(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        bill = self.dal.fetch_one(
            "SELECT is_deleted FROM unified_bills WHERE id = ?", (bill_id,)
        )
        if not bill:
            return self.err('账单不存在')
        if bill['is_deleted'] == 1:
            return self.err('账单已在回收站中')

        with self.dal.transaction():
            # 处理合并组级联（修复同组其他记录的状态）
            self._handle_merge_group_cascade([bill_id])
            # 清理被删账单自身的合并账务数据，恢复后以干净状态重新开始
            self.dal.update(
                'bill_accounting',
                {
                    'merge_status': 'normal',
                    'merged_group_id': None,
                    'real_payer_account_id': None,
                    'original_counterparty': None,
                    'original_product_desc': None,
                },
                'bill_id = ?',
                (bill_id,),
            )
            self.dal.update(
                'unified_bills',
                {'is_deleted': 1, 'updated_at': self._now()},
                'id = ?',
                (bill_id,),
            )
        return self.ok({'deleted_id': bill_id})

    def restore_bill(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        bill = self.dal.fetch_one(
            "SELECT is_deleted FROM unified_bills WHERE id = ?", (bill_id,)
        )
        if not bill:
            return self.err('账单不存在')
        if bill['is_deleted'] == 0:
            return self.err('账单未被删除')

        self.dal.update(
            'unified_bills',
            {'is_deleted': 0, 'updated_at': self._now()},
            'id = ?',
            (bill_id,),
        )
        return self.ok({'restored_id': bill_id})

    def permanent_delete_bill(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        bill = self.dal.fetch_one(
            "SELECT id FROM unified_bills WHERE id = ?", (bill_id,)
        )
        if not bill:
            return self.err('账单不存在')

        with self.dal.transaction():
            # 先处理合并组级联（修复同组其他记录的状态）
            self._handle_merge_group_cascade([bill_id])
            self.dal.execute(
                "DELETE FROM bill_accounting WHERE bill_id = ?", (bill_id,)
            )
            self.dal.execute(
                "DELETE FROM source_bills WHERE bill_id = ?", (bill_id,)
            )
            self.dal.execute(
                "DELETE FROM snapshot_details WHERE bill_id = ?", (bill_id,)
            )
            self.dal.execute(
                "DELETE FROM unified_bills WHERE id = ?", (bill_id,)
            )
        return self.ok({'deleted_id': bill_id})

    def get_deleted_bills(self, params=None) -> dict:
        p = params or {}
        page = p.get('page', 1)
        page_size = p.get('page_size', 20)
        return self.query_bills(
            {'filters': {'is_deleted': 1}, 'page': page, 'page_size': page_size}
        )

    def restore_deleted_bills(self, params=None) -> dict:
        bill_ids = (params or {}).get('bill_ids', [])
        if not bill_ids:
            return self.err('未指定账单')
        placeholders = ', '.join(['?' for _ in bill_ids])
        updated = self.dal.execute(
            f"UPDATE unified_bills SET is_deleted = 0, updated_at = ? "
            f"WHERE id IN ({placeholders}) AND is_deleted = 1",
            (self._now(), *bill_ids),
        )
        return self.ok({'restored_count': updated.rowcount})

    def permanent_delete_bills(self, params=None) -> dict:
        bill_ids = (params or {}).get('bill_ids', [])
        if not bill_ids:
            return self.err('未指定账单')
        total = 0
        for bill_id in bill_ids:
            r = self.permanent_delete_bill({'bill_id': bill_id})
            if r.get('success'):
                total += 1
        return self.ok({'deleted_count': total})

    def empty_recycle_bin(self, params=None) -> dict:
        try:
            with self.dal.transaction():
                bills = self.dal.fetch_all(
                    "SELECT id FROM unified_bills WHERE is_deleted = 1"
                )
                bill_ids = [b['id'] for b in bills]
                if bill_ids:
                    # 先处理合并组级联（修复同组其他记录的状态）
                    self._handle_merge_group_cascade(bill_ids)
                    placeholders = ', '.join(['?' for _ in bill_ids])
                    self.dal.execute(
                        f"DELETE FROM bill_accounting WHERE bill_id IN ({placeholders})",
                        tuple(bill_ids),
                    )
                    self.dal.execute(
                        f"DELETE FROM source_bills WHERE bill_id IN ({placeholders})",
                        tuple(bill_ids),
                    )
                    self.dal.execute(
                        f"DELETE FROM snapshot_details WHERE bill_id IN ({placeholders})",
                        tuple(bill_ids),
                    )
                self.dal.execute("DELETE FROM unified_bills WHERE is_deleted = 1")
            return self.ok({'deleted_count': len(bill_ids)})
        except Exception as e:
            return self.err(f'清空回收站失败: {e}')

    # ─── 6.2.10 批量操作与角色分配 ────────────────────────────

    def batch_reassign_bills(self, params=None) -> dict:
        p = params or {}
        bill_ids = p.get('bill_ids', [])
        account_id = p.get('account_id')
        if not bill_ids:
            return self.err('未指定账单')

        try:
            with self.dal.transaction():
                account = self.dal.fetch_one(
                    "SELECT role_id FROM accounts WHERE id = ?", (account_id,)
                )
                if not account:
                    return self.err('账户不存在')

                new_role_id = account['role_id']
                new_assign_status = 'assigned' if new_role_id else 'pending'

                snapshot_id = self.snapshot.create_snapshot(
                    'batch_reassign',
                    f'批量修改{len(bill_ids)}条账单的账户为{account_id}',
                    bill_ids,
                )

                placeholders = ', '.join(['?' for _ in bill_ids])
                self.dal.execute(
                    f"UPDATE unified_bills SET account_id = ?, role_id = ?, "
                    f"assign_status = ?, updated_at = ? WHERE id IN ({placeholders})",
                    (account_id, new_role_id, new_assign_status,
                     self._now(), *bill_ids),
                )

                self.snapshot.finalize_snapshot(snapshot_id, bill_ids)

            return self.ok({
                'updated_count': len(bill_ids),
                'snapshot_id': snapshot_id,
            })
        except Exception as e:
            return self.err(f'批量重分配失败: {e}')

    def reassign_bill_family(self, params=None) -> dict:
        return self.err('账单归属家庭功能已下线，请改为调整角色归属')

    def rollback_batch(self, params=None) -> dict:
        batch_id = (params or {}).get('batch_id')
        if not batch_id:
            return self.err('未指定批次')

        try:
            with self.dal.transaction():
                bills = self.dal.fetch_all(
                    "SELECT id FROM unified_bills WHERE batch_id = ?", (batch_id,)
                )
                bill_ids = [b['id'] for b in bills]
                if not bill_ids:
                    return self.err('该批次无账单数据')

                # 先处理合并组级联（修复同组其他记录的状态）
                self._handle_merge_group_cascade(bill_ids)

                placeholders = ', '.join(['?' for _ in bill_ids])
                self.dal.execute(
                    f"DELETE FROM bill_accounting WHERE bill_id IN ({placeholders})",
                    tuple(bill_ids),
                )
                self.dal.execute(
                    f"DELETE FROM source_bills WHERE bill_id IN ({placeholders})",
                    tuple(bill_ids),
                )
                self.dal.execute(
                    "DELETE FROM unified_bills WHERE batch_id = ?", (batch_id,),
                )
                self.dal.update(
                    'collection_records',
                    {'batch_id': None, 'status': 'pending', 'parse_result': None, 'error_msg': None},
                    'batch_id = ?',
                    (batch_id,),
                )
                self.dal.execute(
                    "DELETE FROM import_batches WHERE batch_id = ?", (batch_id,),
                )

            return self.ok({'deleted_count': len(bill_ids)})
        except Exception as e:
            return self.err(f'回退失败: {e}')

    # ─── 6.2.11 角色-家庭关联 ────────────────────────────

    def get_role_families(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        rows = self.dal.fetch_all(
            "SELECT rf.*, f.name as family_name FROM role_families rf "
            "JOIN families f ON rf.family_id = f.id WHERE rf.role_id = ?",
            (role_id,),
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def add_role_family(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        family_id = p.get('family_id')
        try:
            with self.dal.transaction():
                self.dal.insert_or_ignore('role_families', {
                    'role_id': role_id,
                    'family_id': family_id,
                })
            return self.ok()
        except Exception as e:
            return self.err(f'添加角色-家庭关联失败: {e}')

    def remove_role_family(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        family_id = p.get('family_id')
        rf = self.dal.fetch_one(
            "SELECT 1 FROM role_families WHERE role_id = ? AND family_id = ?",
            (role_id, family_id),
        )
        if not rf:
            return self.err('关联不存在')

        self.dal.delete(
            'role_families',
            'role_id = ? AND family_id = ?',
            (role_id, family_id),
        )
        return self.ok()

    # ─── 6.2.12 采集记录删除 ────────────────────────────

    def delete_collection_records(self, params=None) -> dict:
        """仅删除采集记录，需满足：未解析 或 关联账单已删除"""
        record_ids = (params or {}).get('record_ids', [])
        if not record_ids:
            return self.err('未指定采集记录')

        deleted_count = 0
        blocked = []
        for record_id in record_ids:
            record = self.dal.fetch_one(
                "SELECT status, batch_id FROM collection_records WHERE id = ?", (record_id,)
            )
            if not record:
                blocked.append({'id': record_id, 'reason': '记录不存在'})
                continue

            # 未解析状态直接可删
            if record['status'] == 'pending':
                self.dal.delete('collection_records', 'id = ?', (record_id,))
                deleted_count += 1
                continue

            # 已解析状态需检查账单是否已删除
            if record['batch_id']:
                bills_exist = self.dal.fetch_one(
                    "SELECT COUNT(*) as cnt FROM unified_bills WHERE batch_id = ? AND is_deleted = 0",
                    (record['batch_id'],)
                )
                if bills_exist and bills_exist['cnt'] > 0:
                    blocked.append({'id': record_id, 'reason': '关联账单未删除'})
                    continue

            self.dal.delete('collection_records', 'id = ?', (record_id,))
            deleted_count += 1

        return self.ok({'deleted_count': deleted_count, 'blocked': blocked})

    def delete_bills_by_collections(self, params=None) -> dict:
        """
        仅删除关联账单，保留采集记录。
        外键依赖关系（删除顺序必须严格遵守）：
          unified_bills.source_bill_id → source_bills(id)  [循环]
          bill_accounting.bill_id → unified_bills(id)
          bill_accounting.merged_group_id 关联同一合并组的记录
          source_bills.bill_id → unified_bills(id)
          collection_records.batch_id → import_batches(batch_id)
        正确顺序：
          1. 解除合并组关联（merged_group_id）
          2. 解除 source_bill_id 循环引用
          3. 删除 bill_accounting（引用 unified_bills）
          4. 删除 snapshot_details
          5. 删除 source_bills（引用 unified_bills，此时 unified_bills 不再引用 source_bills）
          6. 删除 unified_bills（此时无表引用它）
          7. 解除 collection_records.batch_id 引用
          8. 删除 import_batches
        """
        record_ids = (params or {}).get('record_ids', [])
        if not record_ids:
            return self.err('未指定采集记录')

        deleted_count = 0

        try:
            with self.dal.transaction():
                # 收集所有 batch_id
                batch_ids = []
                for record_id in record_ids:
                    record = self.dal.fetch_one(
                        "SELECT batch_id FROM collection_records WHERE id = ?", (record_id,)
                    )
                    if record and record['batch_id']:
                        batch_ids.append(record['batch_id'])

                if not batch_ids:
                    return self.ok({'deleted_count': 0})

                # 收集所有 bill_ids
                all_bill_ids = []
                for batch_id in batch_ids:
                    bills = self.dal.fetch_all(
                        "SELECT id FROM unified_bills WHERE batch_id = ?", (batch_id,)
                    )
                    all_bill_ids.extend([b['id'] for b in bills])

                if all_bill_ids:
                    placeholders = ', '.join(['?' for _ in all_bill_ids])
                    bill_params = tuple(all_bill_ids)

                    # 1. 解除合并组关联（merged_group_id）
                    # 使用统一的级联处理：merged_target → normal, merged_source → orphan
                    self._handle_merge_group_cascade(all_bill_ids)
                    # 2. 解除 source_bill_id 循环引用（unified_bills → source_bills）
                    self.dal.execute(
                        f"UPDATE unified_bills SET source_bill_id = NULL WHERE id IN ({placeholders})",
                        bill_params
                    )
                    # 3. 删除 bill_accounting（引用 unified_bills.id）
                    self.dal.execute(
                        f"DELETE FROM bill_accounting WHERE bill_id IN ({placeholders})",
                        bill_params
                    )
                    # 4. 删除 snapshot_details
                    self.dal.execute(
                        f"DELETE FROM snapshot_details WHERE bill_id IN ({placeholders})",
                        bill_params
                    )
                    # 5. 删除 source_bills（引用 unified_bills.id，此时已无反向引用）
                    self.dal.execute(
                        f"DELETE FROM source_bills WHERE bill_id IN ({placeholders})",
                        bill_params
                    )
                    # 6. 删除 unified_bills（此时无表再引用它）
                    batch_placeholders = ', '.join(['?' for _ in batch_ids])
                    self.dal.execute(
                        f"DELETE FROM unified_bills WHERE batch_id IN ({batch_placeholders})",
                        tuple(batch_ids)
                    )
                    deleted_count = len(all_bill_ids)

                # 7. 解除 collection_records 对 import_batches 的外键引用
                batch_placeholders = ', '.join(['?' for _ in batch_ids])
                self.dal.execute(
                    f"UPDATE collection_records SET batch_id = NULL, status = 'pending', parse_result = NULL WHERE batch_id IN ({batch_placeholders})",
                    tuple(batch_ids)
                )
                # 8. 删除 import_batches
                self.dal.execute(
                    f"DELETE FROM import_batches WHERE batch_id IN ({batch_placeholders})",
                    tuple(batch_ids)
                )

            return self.ok({'deleted_count': deleted_count})
        except Exception as e:
            return self.err(f'删除失败: {e}')
