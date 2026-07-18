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
from core.trade_types import VALID_TRADE_TYPES, TRADE_TYPE_LABELS, get_trade_type_label
from modules.accounting.credit_tracker import CreditTracker
from modules.accounting.cross_platform_merger import CrossPlatformMerger
from modules.accounting.transfer_pairer import TransferPairer


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('audit')


def audit_log(operation: str):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            params = args[0] if args else kwargs.get('params')
            try:
                params_str = json.dumps(params, ensure_ascii=False, default=str)[:500]
            except Exception as e:
                params_str = f"<serialization_failed: {e}>"
            audit_logger.info(
                "operation=%s params=%s caller=%s",
                operation,
                params_str,
                func.__name__,
            )
            result = func(self, *args, **kwargs)
            audit_logger.info(
                "operation=%s success=%s message=%s",
                operation,
                result.get('success', False),
                result.get('message', '')[:200],
            )
            return result
        return wrapper
    return decorator


class BridgeBase:
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

    def _build_bill_conditions(self, filters=None) -> tuple[str, list]:
        filters = filters or {}
        conditions = ["ub.is_deleted = 0"]
        sql_params = []

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
            conditions.append("ub.trade_time < ?")
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
        if str(filters.get('is_uncategorized', '')).lower() in ('1', 'true'):
            from modules.categorizer import CategoryService
            fallback_category_id = CategoryService(self.dal).get_other_expense_category_id()
            if fallback_category_id is None:
                conditions.append("ub.category_id IS NULL")
            else:
                conditions.append(
                    "(ub.category_id IS NULL OR (ub.category_id = ? AND ub.category_source = 'auto' "
                    "AND ub.category_rule_id IS NULL AND ub.is_category_manual_edited = 0))"
                )
                sql_params.append(fallback_category_id)
        if str(filters.get('is_internal_flow', '')).lower() in ('1', 'true'):
            conditions.append("ub.trade_type IN ('transfer_out', 'transfer_in', 'repayment', 'repayment_mirror')")
        if filters.get('keyword'):
            conditions.append("(ub.counterparty LIKE ? OR ub.product_desc LIKE ? OR ub.remark LIKE ?)")
            kw = f"%{filters['keyword']}%"
            sql_params.extend([kw, kw, kw])
        if filters.get('is_deleted') is not None:
            conditions.append("ub.is_deleted = ?")
            sql_params.append(int(filters['is_deleted']))

        return " AND ".join(conditions), sql_params

    def _validate_existing_id(self, table: str, record_id):
        if not record_id:
            return None
        row = self.dal.fetch_one(f"SELECT id FROM {table} WHERE id = ?", (record_id,))
        return record_id if row else None

    def _validate_string_field(self, value: str | None, max_length: int, field_name: str) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        if len(value) > max_length:
            return None, f'{field_name}长度不能超过{max_length}字符'
        return value.strip() if value else None, None

    def _validate_amount(self, amount: int | str | None) -> tuple[int | None, str | None]:
        if amount is None:
            return None, '金额不能为空'
        try:
            amount_int = int(amount)
        except (TypeError, ValueError):
            return None, '金额格式无效'
        if amount_int <= 0:
            return None, '金额必须大于0'
        if amount_int > 10000000000:
            return None, '金额超出合理范围'
        return amount_int, None

    def _validate_trade_time(self, trade_time: str | None) -> tuple[str | None, str | None]:
        if not trade_time:
            return None, '交易时间不能为空'
        try:
            datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None, '交易时间格式无效'
        return trade_time, None

    def _resolve_bill_assignment(self, account_id=None, role_id=None) -> tuple[int | None, int | None, str]:
        resolved_account_id = self._validate_existing_id('accounts', account_id)
        resolved_role_id = None

        if resolved_account_id:
            account = self.dal.fetch_one("SELECT role_id FROM accounts WHERE id = ?", (resolved_account_id,))
            if account and account['role_id']:
                resolved_role_id = self._validate_existing_id('roles', account['role_id'])
        elif role_id:
            resolved_role_id = self._validate_existing_id('roles', role_id)

        assign_status = 'assigned' if (resolved_account_id and resolved_role_id) else 'pending'
        return resolved_account_id, resolved_role_id, assign_status

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
            merger = CrossPlatformMerger(self.dal)
            merge_result = merger.mark_orphan(dict(bill)) or {}
            if merge_result.get('merged'):
                post_actions.append('auto_merged_source')
            elif merge_result.get('orphan'):
                post_actions.append('mark_orphan')
        elif bill.get('channel') == 'ccb':
            merger = CrossPlatformMerger(self.dal)
            merge_result = merger.try_merge(dict(bill)) or {}
            if merge_result.get('merged'):
                post_actions.append('auto_merged_target')

        if bill.get('trade_type') in ('transfer_out', 'transfer_in'):
            accounting = self.dal.fetch_one(
                "SELECT transfer_link_id FROM bill_accounting WHERE bill_id = ?", (bill_id,)
            )
            if not accounting or not accounting.get('transfer_link_id'):
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
