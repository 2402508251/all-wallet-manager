"""ApiBridge domain mixin."""
import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta

from core.db_rebuild import rebuild_database
from core.dal import DAL
from core.snapshot import SnapshotEngine
from core.trade_types import VALID_TRADE_TYPES, TRADE_TYPE_LABELS, get_trade_type_label
from modules.accounting.credit_tracker import CreditTracker
from modules.accounting.cross_platform_merger import CrossPlatformMerger
from modules.accounting.transfer_pairer import TransferPairer

from .bridge_base import DateTimeEncoder, audit_log, logger


class AdminBridgeMixin:
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

    def create_snapshot(self, params=None) -> dict:
        description = ((params or {}).get('description') or '').strip()
        if not description:
            description = f"手动快照 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        MAX_SNAPSHOT_BILLS = 500
        bill_ids = self.dal.fetch_all(
            "SELECT id FROM unified_bills WHERE is_deleted = 0 AND is_system = 0 LIMIT ?",
            (MAX_SNAPSHOT_BILLS + 1,),
        )
        if not bill_ids:
            return self.err('暂无可创建快照的账单')
        
        ids = [r['id'] for r in bill_ids]
        warning = None
        if len(ids) > MAX_SNAPSHOT_BILLS:
            ids = ids[:MAX_SNAPSHOT_BILLS]
            warning = f'账单数量超过{MAX_SNAPSHOT_BILLS}条，仅快照前{MAX_SNAPSHOT_BILLS}条'
        
        snapshot_id = self.snapshot.create_snapshot('manual', description, ids)
        self.snapshot.finalize_snapshot(snapshot_id, ids)
        
        result = {
            'snapshot_id': snapshot_id,
            'bill_count': len(ids),
            'description': description,
            'snapshot_type': 'manual',
        }
        if warning:
            result['warning'] = warning
        return self.ok(result)

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

    @audit_log('reset_application')
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
            logger.exception("reset_application failed")
            try:
                self.db.initialize()
                self.dal = DAL(self.db)
                self.snapshot = SnapshotEngine(self.db, dal=self.dal)
                self._account_cache.clear()
                self._default_ids = None
            except Exception as recover_err:
                logger.error(f"Failed to recover after reset failure: {recover_err}")
            return self.err(f'重置失败: {e}')

    @audit_log('clear_all_bills')
    def clear_all_bills(self, params=None) -> dict:
        try:
            with self.dal.transaction():
                # 先收集所有账单ID并处理合并组级联
                all_bills = self.dal.fetch_all("SELECT id FROM unified_bills")
                all_bill_ids = [b['id'] for b in all_bills]
                if all_bill_ids:
                    self._handle_merge_group_cascade(all_bill_ids)
                self.dal.execute("DELETE FROM transfer_pair_decisions")
                self.dal.execute("DELETE FROM bill_accounting")
                self.dal.execute("DELETE FROM source_bills")
                self.dal.execute("DELETE FROM unified_bills")
                self.dal.execute(
                    "UPDATE collection_records SET status = 'pending', batch_id = NULL, parse_result = NULL"
                )
                self.dal.execute("DELETE FROM import_batches")
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
                            f"DELETE FROM transfer_pair_decisions WHERE out_bill_id IN ({placeholders}) OR in_bill_id IN ({placeholders})",
                            tuple(bill_ids) + tuple(bill_ids)
                        )
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

    @audit_log('delete_bill')
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

    @audit_log('restore_bill')
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

    @audit_log('permanent_delete_bill')
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
                    f"DELETE FROM transfer_pair_decisions WHERE out_bill_id IN ({placeholders}) OR in_bill_id IN ({placeholders})",
                    tuple(bill_ids) + tuple(bill_ids),
                )
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
