"""
跨平台支付合并 —— 将支付宝/微信第三方支付与银行卡扣款记录合并
"""
import uuid
from datetime import datetime

from core.dal import DAL


class CrossPlatformMerger:
    THIRD_PARTY_KEYWORDS = ['微信', '支付宝', '财付通', 'Alipay', 'WeChat']
    TIME_THRESHOLD_HOURS = 48

    def __init__(self, dal: DAL):
        self.dal = dal

    def scan_orphans(self) -> list[dict]:
        rows = self.dal.fetch_all(
            "SELECT ub.*, ba.merge_status, ba.transfer_link_id "
            "FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ba.merge_status = 'orphan' AND ub.is_deleted = 0 "
            "ORDER BY ub.trade_time DESC"
        )
        return [dict(r) for r in rows]

    def try_merge(self, bank_record: dict) -> dict | None:
        amount = bank_record.get('amount_cents', 0)
        trade_time = bank_record.get('trade_time', '')
        product_desc = bank_record.get('product_desc', '')
        remark = bank_record.get('remark', '')
        channel = bank_record.get('channel', '')

        if channel != 'ccb':
            return None

        search_text = f"{product_desc} {remark}"
        is_third_party = any(kw in search_text for kw in self.THIRD_PARTY_KEYWORDS)
        if not is_third_party:
            return None

        orphans = self.dal.fetch_all(
            "SELECT ub.*, ba.id as accounting_id "
            "FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ba.merge_status = 'orphan' AND ub.is_deleted = 0 "
            "AND ub.amount_cents = ? AND ub.direction = ?",
            (amount, bank_record.get('direction', 'expense')),
        )

        best_match = None
        best_time_diff = float('inf')

        for orphan in orphans:
            try:
                t1 = datetime.fromisoformat(trade_time)
                t2 = datetime.fromisoformat(orphan['trade_time'])
                diff_hours = abs((t1 - t2).total_seconds()) / 3600
                if diff_hours <= self.TIME_THRESHOLD_HOURS and diff_hours < best_time_diff:
                    best_time_diff = diff_hours
                    best_match = orphan
            except (ValueError, TypeError):
                continue

        if not best_match:
            return None

        bank_counterparty = bank_record.get('counterparty', '')
        bank_product_desc = product_desc
        third_party_counterparty = best_match['counterparty'] or ''
        third_party_product_desc = best_match['product_desc'] or ''

        DEFAULT_COUNTERPARTIES = {'银联', '', '—', '-'}

        if not bank_counterparty or bank_counterparty in DEFAULT_COUNTERPARTIES:
            new_counterparty = third_party_counterparty
        else:
            new_counterparty = f"{bank_counterparty} | {third_party_counterparty}" if third_party_counterparty else bank_counterparty

        channel_label = '微信' if '微信' in search_text or 'WeChat' in search_text else '支付宝'
        new_product_desc = f"{bank_product_desc} | [{channel_label}] {third_party_product_desc}" if third_party_product_desc else bank_product_desc

        self.dal.update(
            'unified_bills',
            {
                'counterparty': new_counterparty,
                'product_desc': new_product_desc,
            },
            'id = ?',
            (bank_record.get('id'),),
        )

        existing_accounting = self.dal.fetch_one(
            "SELECT id FROM bill_accounting WHERE bill_id = ?",
            (bank_record.get('id'),),
        )
        if existing_accounting:
            self.dal.update(
                'bill_accounting',
                {
                    'merge_status': 'normal',
                    'original_counterparty': bank_counterparty,
                    'original_product_desc': bank_product_desc,
                },
                'bill_id = ?',
                (bank_record.get('id'),),
            )
        else:
            self.dal.insert('bill_accounting', {
                'bill_id': bank_record.get('id'),
                'merge_status': 'normal',
                'original_counterparty': bank_counterparty,
                'original_product_desc': bank_product_desc,
            })

        self.dal.update(
            'unified_bills',
            {'is_deleted': 1, 'role_id': None, 'family_id': None},
            'id = ?',
            (best_match['id'],),
        )

        self.dal.update(
            'bill_accounting',
            {'merge_status': 'merged_source', 'merged_to_id': bank_record.get('id')},
            'bill_id = ?',
            (best_match['id'],),
        )

        return {
            'merged': True,
            'bank_bill_id': bank_record.get('id'),
            'third_party_bill_id': best_match['id'],
        }

    def mark_orphan(self, third_party_record: dict) -> dict:
        bill_id = third_party_record.get('id')
        if not bill_id:
            return {'marked': True, 'orphan': True}

        existing = self.dal.fetch_one(
            "SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,)
        )
        if existing:
            self.dal.update(
                'bill_accounting',
                {'merge_status': 'orphan'},
                'bill_id = ?',
                (bill_id,),
            )
        else:
            self.dal.insert('bill_accounting', {
                'bill_id': bill_id,
                'merge_status': 'orphan',
            })

        return {'marked': True, 'orphan': True}

    def undo_merge(self, merged_source_id: int) -> dict:
        accounting = self.dal.fetch_one(
            "SELECT * FROM bill_accounting WHERE bill_id = ? AND merge_status = 'merged_source'",
            (merged_source_id,),
        )
        if not accounting:
            return {'success': False, 'message': '未找到合并源记录'}

        merged_to_id = accounting['merged_to_id']

        source_bill = self.dal.fetch_one(
            "SELECT account_id FROM unified_bills WHERE id = ?",
            (merged_source_id,),
        )
        restore_fields = {'is_deleted': 0}
        if source_bill and source_bill['account_id']:
            account = self.dal.fetch_one(
                "SELECT role_id FROM accounts WHERE id = ?",
                (source_bill['account_id'],),
            )
            if account and account['role_id']:
                restore_fields['role_id'] = account['role_id']
                primary_family = self.dal.fetch_one(
                    "SELECT family_id FROM role_families "
                    "WHERE role_id = ? AND is_primary = 1",
                    (account['role_id'],),
                )
                if primary_family:
                    restore_fields['family_id'] = primary_family['family_id']

        self.dal.update(
            'unified_bills',
            restore_fields,
            'id = ?',
            (merged_source_id,),
        )

        self.dal.update(
            'bill_accounting',
            {'merge_status': 'orphan', 'merged_to_id': None},
            'bill_id = ?',
            (merged_source_id,),
        )

        if merged_to_id:
            target_accounting = self.dal.fetch_one(
                "SELECT original_counterparty, original_product_desc "
                "FROM bill_accounting WHERE bill_id = ?",
                (merged_to_id,),
            )
            if target_accounting:
                restore_data = {}
                if target_accounting['original_counterparty'] is not None:
                    restore_data['counterparty'] = target_accounting['original_counterparty']
                if target_accounting['original_product_desc'] is not None:
                    restore_data['product_desc'] = target_accounting['original_product_desc']
                if restore_data:
                    self.dal.update(
                        'unified_bills',
                        restore_data,
                        'id = ?',
                        (merged_to_id,),
                    )

            self.dal.delete(
                'bill_accounting',
                'bill_id = ? AND original_counterparty IS NOT NULL',
                (merged_to_id,),
            )

        return {'success': True, 'restored_bill_id': merged_source_id}