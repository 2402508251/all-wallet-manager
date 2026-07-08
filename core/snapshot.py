"""
全局快照引擎 —— 数据变更前创建增量 Diff 备份，支持变更对比与一键回退
两表存储：snapshots（快照元信息）+ snapshot_details（逐字段 Diff）
"""
from datetime import datetime
from typing import Optional

from .db import DatabaseManager
from .dal import DAL


class SnapshotEngine:
    TRACKED_TABLES = {
        'unified_bills': [
            'channel', 'trade_time', 'trade_type', 'direction', 'amount_cents',
            'counterparty', 'product_desc', 'payment_method', 'status',
            'channel_trade_no', 'remark', 'account_id',
            'role_id', 'category_id', 'category_source', 'category_score',
            'category_rule_id', 'is_category_manual_edited',
            'assign_status', 'is_deleted', 'is_system',
        ],
        'bill_accounting': [
            'transfer_link_id', 'is_credit', 'credit_account_id',
            'merge_status', 'merged_group_id', 'real_payer_account_id',
            'original_counterparty', 'original_product_desc',
        ],
    }

    def __init__(self, db_manager: DatabaseManager, dal: DAL = None):
        self.db = db_manager
        self.dal = dal if dal else DAL(db_manager)

    def create_snapshot(
        self,
        snapshot_type: str,
        description: str,
        affected_record_ids: list[int],
        batch_id: Optional[str] = None,
    ) -> int:
        """
        第一阶段：操作前快照（全量记录所有字段的 old_value）
        在执行变更操作前调用，记录每条受影响记录的当前状态
        """
        if not affected_record_ids:
            return -1

        with self.dal.transaction():
            now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
            snapshot_id = self.dal.insert('snapshots', {
                'snapshot_type': snapshot_type,
                'description': description,
                'bill_count': len(affected_record_ids),
                'created_at': now,
            })

            details_batch = []
            for table_name, fields in self.TRACKED_TABLES.items():
                if table_name == 'unified_bills':
                    pk_col = 'id'
                    placeholders = ','.join(['?' for _ in affected_record_ids])
                    rows = self.dal.fetch_all(
                        f"SELECT * FROM {table_name} WHERE {pk_col} IN ({placeholders})",
                        tuple(affected_record_ids),
                    )
                elif table_name == 'bill_accounting':
                    pk_col = 'bill_id'
                    placeholders = ','.join(['?' for _ in affected_record_ids])
                    rows = self.dal.fetch_all(
                        f"SELECT * FROM {table_name} WHERE {pk_col} IN ({placeholders})",
                        tuple(affected_record_ids),
                    )
                else:
                    continue

                rows_by_pk = {row[pk_col]: row for row in rows}
                for bill_id in affected_record_ids:
                    row = rows_by_pk.get(bill_id)
                    if row is None:
                        continue

                    for field_name in fields:
                        val = row[field_name] if field_name in row.keys() else None
                        details_batch.append({
                            'snapshot_id': snapshot_id,
                            'bill_id': bill_id,
                            'table_name': table_name,
                            'field_name': field_name,
                            'old_value': str(val) if val is not None else None,
                            'new_value': None,
                            'is_deleted_after': 0,
                        })

            if details_batch:
                self._bulk_insert_details(details_batch)

        return snapshot_id

    def _bulk_insert_details(self, details_batch: list[dict]) -> int:
        if not details_batch:
            return 0

        columns = ['snapshot_id', 'bill_id', 'table_name', 'field_name', 'old_value', 'new_value', 'is_deleted_after']
        placeholders = ','.join(['?' for _ in columns])
        sql = f"INSERT INTO snapshot_details ({','.join(columns)}) VALUES ({placeholders})"

        values = []
        for d in details_batch:
            values.append((
                d['snapshot_id'],
                d['bill_id'],
                d['table_name'],
                d['field_name'],
                d['old_value'],
                d['new_value'],
                d['is_deleted_after'],
            ))

        self.dal.execute_batch(sql, values)
        return len(details_batch)

    def finalize_snapshot(
        self,
        snapshot_id: int,
        affected_record_ids: list[int],
    ) -> int:
        """
        第二阶段：操作后回填 new_value
        在执行变更操作后调用，对比当前值与 old_value，回填 new_value
        未变更的字段保留 old_value=new_value（全量记录，便于回退时直接恢复）
        同时检测记录是否被物理删除（is_deleted_after=1）
        """
        if not affected_record_ids or snapshot_id < 0:
            return 0

        updated = 0
        with self.dal.transaction():
            update_batch = []
            delete_mark_batch = []

            for table_name, fields in self.TRACKED_TABLES.items():
                if table_name == 'unified_bills':
                    pk_col = 'id'
                    placeholders = ','.join(['?' for _ in affected_record_ids])
                    rows = self.dal.fetch_all(
                        f"SELECT * FROM {table_name} WHERE {pk_col} IN ({placeholders})",
                        tuple(affected_record_ids),
                    )
                elif table_name == 'bill_accounting':
                    pk_col = 'bill_id'
                    placeholders = ','.join(['?' for _ in affected_record_ids])
                    rows = self.dal.fetch_all(
                        f"SELECT * FROM {table_name} WHERE {pk_col} IN ({placeholders})",
                        tuple(affected_record_ids),
                    )
                else:
                    continue

                rows_by_pk = {row[pk_col]: row for row in rows}
                for bill_id in affected_record_ids:
                    row = rows_by_pk.get(bill_id)

                    if row is None:
                        delete_mark_batch.append((snapshot_id, bill_id, table_name))
                        updated += len(fields)
                        continue

                    for field_name in fields:
                        val = row[field_name] if field_name in row.keys() else None
                        new_val_str = str(val) if val is not None else None
                        update_batch.append((new_val_str, snapshot_id, bill_id, table_name, field_name))
                        updated += 1

            if delete_mark_batch:
                self.dal.execute_batch(
                    "UPDATE snapshot_details SET is_deleted_after = 1 "
                    "WHERE snapshot_id = ? AND bill_id = ? AND table_name = ?",
                    delete_mark_batch,
                )

            if update_batch:
                self.dal.execute_batch(
                    "UPDATE snapshot_details SET new_value = ? "
                    "WHERE snapshot_id = ? AND bill_id = ? "
                    "AND table_name = ? AND field_name = ?",
                    update_batch,
                )

        return updated

    def record_changes(
        self,
        snapshot_id: int,
        bill_id: int,
        table_name: str,
        changes: dict,
    ) -> None:
        for field_name, (old_val, new_val) in changes.items():
            existing = self.dal.fetch_one(
                "SELECT id FROM snapshot_details "
                "WHERE snapshot_id = ? AND bill_id = ? "
                "AND table_name = ? AND field_name = ?",
                (snapshot_id, bill_id, table_name, field_name),
            )
            if existing:
                self.dal.update(
                    'snapshot_details',
                    {'new_value': str(new_val) if new_val is not None else None},
                    'id = ?',
                    (existing['id'],),
                )
            else:
                self.dal.insert('snapshot_details', {
                    'snapshot_id': snapshot_id,
                    'bill_id': bill_id,
                    'table_name': table_name,
                    'field_name': field_name,
                    'old_value': str(old_val) if old_val is not None else None,
                    'new_value': str(new_val) if new_val is not None else None,
                })

    def restore_snapshot(self, snapshot_id: int) -> dict:
        """
        全量恢复：将所有字段恢复到 old_value 状态
        对于 is_deleted_after=1 的记录，需重新插入（目前仅标记，暂不实现重建逻辑）
        """
        snapshot = self.dal.fetch_one(
            "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
        )
        if snapshot is None:
            return {'success': False, 'message': '快照不存在'}

        details = self.dal.fetch_all(
            "SELECT * FROM snapshot_details WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        if not details:
            return {'success': False, 'message': '快照无变更明细'}

        grouped = {}
        deleted_records = set()
        for d in details:
            key = (d['bill_id'], d['table_name'])
            if key not in grouped:
                grouped[key] = {}
            grouped[key][d['field_name']] = d['old_value']
            if d['is_deleted_after'] == 1:
                deleted_records.add(key)

        with self.dal.transaction():
            restored_count = 0
            skipped_deleted = 0
            for (bill_id, table_name), fields in grouped.items():
                if table_name == 'unified_bills':
                    pk_col = 'id'
                    pk_val = bill_id
                elif table_name == 'bill_accounting':
                    pk_col = 'bill_id'
                    pk_val = bill_id
                else:
                    continue

                if (bill_id, table_name) in deleted_records:
                    existing = self.dal.fetch_one(
                        f"SELECT id FROM {table_name} WHERE {pk_col} = ?",
                        (pk_val,),
                    )
                    if existing:
                        self.dal.update(
                            table_name,
                            {'is_deleted': 0} if table_name == 'unified_bills' else fields,
                            f'{pk_col} = ?',
                            (pk_val,),
                        )
                        restored_count += 1
                    else:
                        if table_name == 'unified_bills':
                            fields['is_deleted'] = 0
                            fields['id'] = bill_id
                            self.dal.insert(table_name, fields)
                            restored_count += 1
                        elif table_name == 'bill_accounting':
                            fields['bill_id'] = bill_id
                            self.dal.insert(table_name, fields)
                            restored_count += 1
                    skipped_deleted += 1
                    continue

                self.dal.update(
                    table_name,
                    fields,
                    f'{pk_col} = ?',
                    (pk_val,),
                )
                restored_count += 1

        return {
            'success': True,
            'restored_count': restored_count,
            'recovered_deleted_count': skipped_deleted,
            'snapshot_id': snapshot_id,
        }

    def get_snapshot_details(self, snapshot_id: int) -> list[dict]:
        details = self.dal.fetch_all(
            "SELECT * FROM snapshot_details WHERE snapshot_id = ? "
            "ORDER BY bill_id, table_name, field_name",
            (snapshot_id,),
        )
        return [dict(d) for d in details]

    def list_snapshots(self, limit: int = 20) -> list[dict]:
        rows = self.dal.fetch_all(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def delete_snapshot(self, snapshot_id: int) -> bool:
        snapshot = self.dal.fetch_one(
            "SELECT id FROM snapshots WHERE id = ?", (snapshot_id,)
        )
        if snapshot is None:
            return False

        with self.dal.transaction():
            self.dal.delete('snapshot_details', 'snapshot_id = ?', (snapshot_id,))
            self.dal.delete('snapshots', 'id = ?', (snapshot_id,))
        return True

    def cleanup_old_snapshots(self, keep_count: int = 50) -> int:
        row = self.dal.fetch_one("SELECT COUNT(*) as cnt FROM snapshots")
        total = row['cnt'] if row else 0
        if total <= keep_count:
            return 0

        cutoff = self.dal.fetch_one(
            "SELECT id FROM snapshots ORDER BY id DESC LIMIT 1 OFFSET ?",
            (keep_count - 1,),
        )
        if cutoff is None:
            return 0

        cutoff_id = cutoff['id']
        with self.dal.transaction():
            old_details = self.dal.fetch_all(
                "SELECT DISTINCT snapshot_id FROM snapshot_details WHERE snapshot_id < ?",
                (cutoff_id,),
            )
            for d in old_details:
                self.dal.delete('snapshot_details', 'snapshot_id = ?', (d['snapshot_id'],))

            deleted = self.dal.delete('snapshots', 'id < ?', (cutoff_id,))
        return deleted