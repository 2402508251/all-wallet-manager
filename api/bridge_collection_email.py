"""ApiBridge domain mixin."""
import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta

from core.db_rebuild import rebuild_database
from core.trade_types import VALID_TRADE_TYPES, TRADE_TYPE_LABELS, get_trade_type_label
from modules.accounting.credit_tracker import CreditTracker
from modules.accounting.cross_platform_merger import CrossPlatformMerger
from modules.accounting.transfer_pairer import TransferPairer

from .bridge_base import DateTimeEncoder, audit_log, logger


class CollectionEmailBridgeMixin:
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
            return self.ok({
                'record_ids': record_ids,
                'count': len(record_ids),
                'duplicate_skipped': handler.duplicate_skipped,
            })
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

            if channel == 'self_export':
                account_info = {'accounts': []}
            else:
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

                    if channel == 'self_export':
                        account_id, role_id, assign_status = self._resolve_bill_assignment(
                            rec.get('account_id'), rec.get('role_id')
                        )
                    else:
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

                    category_id = None
                    if channel == 'self_export':
                        category_id = self._validate_existing_id('bill_categories', rec.get('category_id'))

                    is_manual_category = bool(rec.get('is_category_manual_edited')) or rec.get('category_source') == 'manual'
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
                        'category_id': category_id,
                        'assign_status': assign_status,
                        'is_system': int(rec.get('is_system') or 0),
                        'is_manual_edited': int(rec.get('is_manual_edited') or 0),
                        'is_category_manual_edited': 1 if (category_id and is_manual_category) else 0,
                        'category_source': 'manual' if (category_id and is_manual_category) else 'auto',
                        'category_score': 0,
                        'category_rule_id': None,
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
                            'raw_json': json.dumps(raw.get('raw', raw), ensure_ascii=False, cls=DateTimeEncoder),
                            'created_at': now,
                        })

                    pipeline_result = self._apply_accounting_pipeline(imported_bill, now)
                    post_action = ','.join(pipeline_result.get('post_actions', ['normal_only']))

                    logger.info(
                        "parse_collection post_action=%s bill_id=%s channel=%s batch_id=%s",
                        post_action, bill_id, rec['channel'], batch_id,
                    )

                    if category_id:
                        classified_count += 1
                    else:
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
            logger.exception(f"parse_collection failed for record_id={record_id}")
            try:
                self.dal.update(
                    'collection_records',
                    {'status': 'error', 'error_msg': str(e)},
                    'id = ?',
                    (record_id,),
                )
            except Exception as update_err:
                logger.error(f"Failed to update error status: {update_err}")
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
        if channel not in ('wechat', 'alipay', 'ccb', 'self_export'):
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
        result = fetcher.test_connection(config_id)
        if not result.get('success'):
            return self.err(result.get('message') or '邮箱连接测试失败')
        return self.ok(result)

    def fetch_email_bills(self, params=None) -> dict:
        config_id = (params or {}).get('config_id')
        from modules.collection.email_fetch import EmailFetcher
        fetcher = EmailFetcher(self.app_dir, self.dal, self.config)
        result = fetcher.fetch_bills(config_id)
        if not result.get('success'):
            return self.err(result.get('message') or '邮箱账单拉取失败')
        return self.ok(result)

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
