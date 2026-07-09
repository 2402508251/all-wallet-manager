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


class AccountingBridgeMixin:
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
            "out_b.account_id AS out_account_id, out_a.account_name AS out_account_name, "
            "in_b.id AS in_bill_id, in_b.trade_time AS in_trade_time, in_b.amount_cents AS in_amount_cents, "
            "in_b.counterparty AS in_counterparty, in_b.channel AS in_channel, in_b.remark AS in_remark, "
            "in_b.account_id AS in_account_id, in_a.account_name AS in_account_name "
            "FROM bill_accounting ba "
            "JOIN unified_bills out_b ON ba.bill_id = out_b.id AND out_b.direction = 'expense' "
            "JOIN bill_accounting ba2 ON ba.transfer_link_id = ba2.transfer_link_id "
            "JOIN unified_bills in_b ON ba2.bill_id = in_b.id AND in_b.direction = 'income' "
            "LEFT JOIN accounts out_a ON out_b.account_id = out_a.id "
            "LEFT JOIN accounts in_a ON in_b.account_id = in_a.id "
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
        if not result.get('success'):
            return self.err(result.get('message', '配对失败'))
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
