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
from core.snapshot import SnapshotEngine
from core.crypto_utils import CredentialEncryptor


logger = logging.getLogger(__name__)


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

    def ensure_default_family_and_role(self) -> dict:
        if self._default_ids is not None:
            return self._default_ids

        with self.dal.transaction():
            family = self.dal.fetch_one(
                "SELECT id FROM families WHERE name = '未分配'"
            )
            if not family:
                family_id = self.dal.insert('families', {'name': '未分配', 'is_default': 1})
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
                    'is_primary': 1,
                })

        self._default_ids = {'role_id': role_id, 'family_id': family_id}
        return self._default_ids

    def get_or_create_account(self, account_tag: str, account_name: str, channel: str) -> int:
        cache_key = f"{account_tag}|{channel}"
        if cache_key in self._account_cache:
            return self._account_cache[cache_key]

        account = self.dal.fetch_one(
            "SELECT id FROM accounts WHERE account_tag = ? AND channel = ?",
            (account_tag, channel),
        )
        if account:
            self._account_cache[cache_key] = account['id']
            return account['id']

        # 确保默认角色存在，新账户自动关联
        defaults = self.ensure_default_family_and_role()
        default_role_id = defaults['role_id']

        account_id = self.dal.insert('accounts', {
            'account_name': account_name,
            'account_tag': account_tag,
            'channel': channel,
            'role_id': default_role_id,
        })

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

            payment_method_to_account = {}
            for acc in account_info.get('accounts', []):
                account_id = self.get_or_create_account(
                    acc['tag'], acc['name'], channel
                )
                payment_method_to_account[acc['payment_method']] = account_id

            batch_id = str(uuid.uuid4())
            now = self._now()

            success_count = 0
            duplicate_count = 0

            with self.dal.transaction():
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
                    if not account_id and '_default_' in payment_method_to_account:
                        account_id = payment_method_to_account['_default_']

                    role_id = None
                    family_id = None
                    if account_id:
                        account = self.dal.fetch_one(
                            "SELECT role_id FROM accounts WHERE id = ?", (account_id,)
                        )
                        if account and account['role_id']:
                            role_id = account['role_id']
                            primary_family = self.dal.fetch_one(
                                "SELECT family_id FROM role_families "
                                "WHERE role_id = ? AND is_primary = 1",
                                (role_id,),
                            )
                            if primary_family:
                                family_id = primary_family['family_id']

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
                        'family_id': family_id,
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

                    post_action = 'normal_only'
                    if rec['channel'] in ('wechat', 'alipay'):
                        from modules.accounting.cross_platform_merger import CrossPlatformMerger
                        merger = CrossPlatformMerger(self.dal)
                        merge_result = merger.mark_orphan(imported_bill) or {}
                        post_action = 'mark_orphan'
                        if merge_result.get('merged'):
                            post_action = 'auto_merged_source'
                    else:
                        self.dal.insert('bill_accounting', {
                            'bill_id': bill_id,
                            'merge_status': 'normal',
                            'created_at': now,
                        })
                        if rec['channel'] == 'ccb':
                            from modules.accounting.cross_platform_merger import CrossPlatformMerger
                            merger = CrossPlatformMerger(self.dal)
                            merge_result = merger.try_merge(imported_bill)
                            if merge_result and merge_result.get('merged'):
                                post_action = 'auto_merged_target'

                    logger.info(
                        "parse_collection post_action=%s bill_id=%s channel=%s batch_id=%s",
                        post_action, bill_id, rec['channel'], batch_id,
                    )

                    success_count += 1

                self.dal.insert('import_batches', {
                    'batch_id': batch_id,
                    'source': record['source_type'],
                    'channel': channel,
                    'file_name': record['file_name'],
                    'total_count': result.total,
                    'success_count': success_count,
                    'duplicate_count': duplicate_count,
                    'import_time': now,
                })

                self.dal.update(
                    'collection_records',
                    {'status': 'parsed', 'batch_id': batch_id,
                     'parse_result': json.dumps({
                         'total': result.total,
                         'success': success_count,
                         'duplicate': duplicate_count,
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
                conditions.append("ub.trade_type = ?")
                sql_params.append(filters['trade_type'])
            if filters.get('start_time'):
                conditions.append("ub.trade_time >= ?")
                sql_params.append(filters['start_time'])
            if filters.get('end_time'):
                conditions.append("ub.trade_time <= ?")
                sql_params.append(filters['end_time'])
            if filters.get('family_id'):
                conditions.append("ub.family_id = ?")
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
            f"bc.name as category_name "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"LEFT JOIN bill_categories bc ON ub.category_id = bc.id "
            f"WHERE {where} ORDER BY ub.trade_time DESC LIMIT ? OFFSET ?",
            tuple(sql_params) + (page_size, offset),
        )

        return self.ok({'total': total, 'list': [dict(r) for r in rows]})

    def get_bill_detail(self, params=None) -> dict:
        bill_id = (params or {}).get('bill_id')
        bill = self.dal.fetch_one(
            "SELECT ub.*, ba.merge_status, ba.transfer_link_id, "
            "ba.is_credit, ba.credit_account_id, ba.merged_group_id, ba.real_payer_account_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
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
            'account_id', 'role_id', 'family_id',
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return self.err('无有效更新字段')

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

    def confirm_transfer_pair(self, params=None) -> dict:
        p = params or {}
        out_id = p.get('out_id')
        in_id = p.get('in_id')
        from modules.accounting.transfer_pairer import TransferPairer
        pairer = TransferPairer(self.dal)
        result = pairer.confirm_pair(out_id, in_id)
        return self.ok(result)

    def reject_transfer_pair(self, params=None) -> dict:
        return self.ok()

    def get_credit_accounts(self, params=None) -> dict:
        rows = self.dal.fetch_all("SELECT * FROM credit_accounts")
        return self.ok({'list': [dict(r) for r in rows]})

    def toggle_hide_repayment_transfer(self, params=None) -> dict:
        hide = (params or {}).get('hide', False)
        return self.ok({'hide': hide})

    # ─── 6.2.6 统计报表 ────────────────────────────

    def get_monthly_summary(self, params=None) -> dict:
        p = params or {}
        year = p.get('year')
        month = p.get('month')
        family_id = p.get('family_id')
        start = f"{year}-{month:02d}-01T00:00:00+08:00"
        if month == 12:
            end = f"{year + 1}-01-01T00:00:00+08:00"
        else:
            end = f"{year}-{month + 1:02d}-01T00:00:00+08:00"

        base_query = "FROM unified_bills ub LEFT JOIN role_families rf ON ub.role_id = rf.role_id AND rf.is_primary = 1"
        conditions = ["ub.is_deleted = 0", "ub.trade_time >= ?", "ub.trade_time < ?"]
        sql_params = [start, end]

        if family_id:
            conditions.append("rf.family_id = ?")
            sql_params.append(family_id)

        where = " AND ".join(conditions)

        income = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {where} AND ub.direction = 'income'",
            tuple(sql_params),
        )['total']

        expense = self.dal.fetch_one(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) as total {base_query} "
            f"WHERE {where} AND ub.direction = 'expense' AND ub.trade_type != 'credit_consumption'",
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
        direction = p.get('direction', 'expense')
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

        if family_id:
            conditions.append("rf.family_id = ?")
            sql_params.append(family_id)

        where = " AND ".join(conditions)

        rows = self.dal.fetch_all(
            f"SELECT bc.name as category_name, bc.icon, "
            f"SUM(ub.amount_cents) as total_amount, COUNT(*) as count "
            f"FROM unified_bills ub "
            f"LEFT JOIN role_families rf ON ub.role_id = rf.role_id AND rf.is_primary = 1 "
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
                'year': current.year, 'month': current.month, 'family_id': family_id
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
                        'role_id': rid, 'family_id': family_id, 'is_primary': 1,
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
        if role_id:
            rows = self.dal.fetch_all(
                "SELECT * FROM accounts WHERE role_id = ?", (role_id,))
        else:
            rows = self.dal.fetch_all("SELECT * FROM accounts")
        return self.ok({'list': [dict(r) for r in rows]})

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
                        new_role_id = data['role_id']
                        new_family_id = None
                        if new_role_id:
                            primary_family = self.dal.fetch_one(
                                "SELECT family_id FROM role_families "
                                "WHERE role_id = ? AND is_primary = 1",
                                (new_role_id,),
                            )
                            if primary_family:
                                new_family_id = primary_family['family_id']

                        bills = self.dal.fetch_all(
                            "SELECT id FROM unified_bills WHERE account_id = ? AND is_deleted = 0",
                            (account_id,),
                        )
                        bill_ids = [b['id'] for b in bills]
                        if bill_ids:
                            self.snapshot.create_snapshot(
                                'account_role_change',
                                f'账户{account_id}角色变更，级联更新{len(bill_ids)}条账单',
                                bill_ids,
                            )

                            new_assign_status = 'assigned' if new_role_id else 'pending'
                            placeholders = ', '.join(['?' for _ in bill_ids])
                            self.dal.execute(
                                f"UPDATE unified_bills SET role_id = ?, family_id = ?, "
                                f"assign_status = ?, updated_at = ? WHERE id IN ({placeholders})",
                                (new_role_id, new_family_id, new_assign_status,
                                 self._now(), *bill_ids),
                            )

                            self.snapshot.finalize_snapshot(
                                self.dal.fetch_one(
                                    "SELECT id FROM snapshots ORDER BY id DESC LIMIT 1"
                                )['id'],
                                bill_ids,
                            )

                self.dal.update('accounts', data, 'id = ?', (account_id,))
            return self.ok()
        except Exception as e:
            return self.err(f'更新账户失败: {e}')

    def delete_account(self, params=None) -> dict:
        account_id = (params or {}).get('account_id')
        self.dal.delete('accounts', 'id = ?', (account_id,))
        return self.ok()

    def get_categories(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT * FROM bill_categories ORDER BY sort_order")
        return self.ok({'list': [dict(r) for r in rows]})

    def create_category(self, params=None) -> dict:
        p = params or {}
        name = p.get('name', '')
        icon = p.get('icon', '')
        parent_id = p.get('parent_id')
        cid = self.dal.insert('bill_categories', {
            'name': name, 'icon': icon, 'parent_id': parent_id,
        })
        return self.ok({'category_id': cid})

    def update_category(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        name = p.get('name')
        icon = p.get('icon')
        sort_order = p.get('sort_order')
        data = {}
        if name is not None:
            data['name'] = name
        if icon is not None:
            data['icon'] = icon
        if sort_order is not None:
            data['sort_order'] = sort_order
        self.dal.update('bill_categories', data, 'id = ?', (category_id,))
        return self.ok()

    def delete_category(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        self.dal.delete('bill_categories', 'id = ?', (category_id,))
        return self.ok()

    def get_category_keywords(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        rows = self.dal.fetch_all(
            "SELECT * FROM category_keywords WHERE category_id = ?",
            (category_id,))
        return self.ok({'list': [dict(r) for r in rows]})

    def save_category_keywords(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        keywords = p.get('keywords', [])
        try:
            with self.dal.transaction():
                self.dal.delete('category_keywords', 'category_id = ?', (category_id,))
                for kw in keywords:
                    self.dal.insert('category_keywords', {
                        'category_id': category_id,
                        'keyword': kw.get('keyword', ''),
                        'match_field': kw.get('match_field', 'counterparty'),
                        'priority': kw.get('priority', 0),
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
                new_family_id = None
                if new_role_id:
                    primary_family = self.dal.fetch_one(
                        "SELECT family_id FROM role_families "
                        "WHERE role_id = ? AND is_primary = 1",
                        (new_role_id,),
                    )
                    if primary_family:
                        new_family_id = primary_family['family_id']

                new_assign_status = 'assigned' if new_role_id else 'pending'

                snapshot_id = self.snapshot.create_snapshot(
                    'batch_reassign',
                    f'批量修改{len(bill_ids)}条账单的账户为{account_id}',
                    bill_ids,
                )

                placeholders = ', '.join(['?' for _ in bill_ids])
                self.dal.execute(
                    f"UPDATE unified_bills SET account_id = ?, role_id = ?, family_id = ?, "
                    f"assign_status = ?, updated_at = ? WHERE id IN ({placeholders})",
                    (account_id, new_role_id, new_family_id, new_assign_status,
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
        p = params or {}
        bill_id = p.get('bill_id')
        family_id = p.get('family_id')
        try:
            with self.dal.transaction():
                bill = self.dal.fetch_one(
                    "SELECT role_id FROM unified_bills WHERE id = ?", (bill_id,)
                )
                if not bill:
                    return self.err('账单不存在')
                if not bill['role_id']:
                    return self.err('账单未分配角色，无法变更家庭')

                rf = self.dal.fetch_one(
                    "SELECT 1 FROM role_families WHERE role_id = ? AND family_id = ?",
                    (bill['role_id'], family_id),
                )
                if not rf:
                    return self.err('目标家庭不是该角色关联的家庭')

                snapshot_id = self.snapshot.create_snapshot(
                    'reassign_family',
                    f'变更账单{bill_id}的归属家庭为{family_id}',
                    [bill_id],
                )

                self.dal.update(
                    'unified_bills',
                    {'family_id': family_id, 'updated_at': self._now()},
                    'id = ?',
                    (bill_id,),
                )

                self.snapshot.finalize_snapshot(snapshot_id, [bill_id])
            return self.ok()
        except Exception as e:
            return self.err(f'变更账单家庭失败: {e}')

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
        is_primary = p.get('is_primary', 0)
        try:
            with self.dal.transaction():
                self.dal.insert_or_ignore('role_families', {
                    'role_id': role_id,
                    'family_id': family_id,
                    'is_primary': is_primary,
                })

                if is_primary == 1:
                    bills = self.dal.fetch_all(
                        "SELECT id FROM unified_bills WHERE role_id = ? AND is_deleted = 0",
                        (role_id,),
                    )
                    bill_ids = [b['id'] for b in bills]
                    if bill_ids:
                        snapshot_id = self.snapshot.create_snapshot(
                            'role_family_change',
                            f'角色{role_id}主要家庭变更，级联更新{len(bill_ids)}条账单',
                            bill_ids,
                        )
                        placeholders = ', '.join(['?' for _ in bill_ids])
                        self.dal.execute(
                            f"UPDATE unified_bills SET family_id = ?, updated_at = ? "
                            f"WHERE id IN ({placeholders})",
                            (family_id, self._now(), *bill_ids),
                        )
                        self.snapshot.finalize_snapshot(snapshot_id, bill_ids)

            return self.ok()
        except Exception as e:
            return self.err(f'添加角色-家庭关联失败: {e}')

    def remove_role_family(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        family_id = p.get('family_id')
        rf = self.dal.fetch_one(
            "SELECT is_primary FROM role_families "
            "WHERE role_id = ? AND family_id = ?",
            (role_id, family_id),
        )
        if not rf:
            return self.err('关联不存在')
        if rf['is_primary'] == 1:
            return self.err('主要家庭不可移除，请先设置其他主要家庭')

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