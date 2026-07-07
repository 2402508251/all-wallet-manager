"""批量重新分类服务。"""
from core.dal import DAL
from core.snapshot import SnapshotEngine
from .service import CategoryService


class CategoryReclassifier:
    def __init__(self, dal: DAL, snapshot: SnapshotEngine):
        self.dal = dal
        self.snapshot = snapshot
        self.service = CategoryService(dal)

    def recategorize(self, scope: dict, only_uncategorized: bool = False, include_income: bool = False) -> dict:
        bill_ids = self._get_scope_bill_ids(scope or {})
        if not bill_ids:
            return {
                'snapshot_id': None,
                'scanned': 0,
                'updated': 0,
                'skipped_manual': 0,
                'unmatched': 0,
            }

        candidates = []
        skipped_manual = 0
        for bill_id in bill_ids:
            bill = self.dal.fetch_one("SELECT * FROM unified_bills WHERE id = ?", (bill_id,))
            if not bill:
                continue
            if bill.get('is_category_manual_edited'):
                skipped_manual += 1
                continue
            if bill.get('is_deleted') or bill.get('is_system'):
                continue
            if not include_income and bill.get('direction') != 'expense':
                continue
            if only_uncategorized and not self._is_unmatched_bill(bill):
                continue
            candidates.append(bill)

        if not candidates:
            return {
                'snapshot_id': None,
                'scanned': len(bill_ids),
                'updated': 0,
                'skipped_manual': skipped_manual,
                'unmatched': 0,
            }

        candidate_ids = [b['id'] for b in candidates]
        snapshot_id = self.snapshot.create_snapshot(
            'recategorize',
            f"重新分类: {(scope or {}).get('type', 'all')}",
            candidate_ids,
        )

        updated = 0
        unmatched = 0
        with self.dal.transaction():
            for bill in candidates:
                result = self.service.categorize_bill(bill['id'], bill=bill)
                if not result.matched:
                    unmatched += 1
                before = (
                    bill.get('category_id'),
                    bill.get('category_source'),
                    bill.get('category_score'),
                    bill.get('category_rule_id'),
                )
                self.service.apply_result(bill['id'], result)
                after = (
                    result.category_id if result.matched else None,
                    'auto' if result.matched else 'none',
                    result.score if result.matched else 0,
                    result.rule_id if result.matched else None,
                )
                if before != after:
                    updated += 1

        self.snapshot.finalize_snapshot(snapshot_id, candidate_ids)
        return {
            'snapshot_id': snapshot_id,
            'scanned': len(bill_ids),
            'updated': updated,
            'skipped_manual': skipped_manual,
            'unmatched': unmatched,
        }

    def _is_unmatched_bill(self, bill: dict) -> bool:
        fallback_category_id = self.service.get_other_expense_category_id()
        return (
            bill.get('direction') == 'expense'
            and not bill.get('is_category_manual_edited')
            and bill.get('category_source') == 'auto'
            and bill.get('category_rule_id') is None
            and fallback_category_id is not None
            and bill.get('category_id') == fallback_category_id
        )

    def _get_scope_bill_ids(self, scope: dict) -> list[int]:
        scope_type = scope.get('type', 'all')
        base_condition = "is_deleted = 0 AND is_system = 0"
        if scope_type == 'all':
            rows = self.dal.fetch_all(f"SELECT id FROM unified_bills WHERE {base_condition}")
        elif scope_type == 'batch':
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE batch_id = ? AND {base_condition}",
                (scope.get('batch_id', ''),),
            )
        elif scope_type == 'channel':
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE channel = ? AND {base_condition}",
                (scope.get('channel', ''),),
            )
        elif scope_type == 'time_range':
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE trade_time >= ? AND trade_time <= ? AND {base_condition}",
                (scope.get('start_time', ''), scope.get('end_time', '')),
            )
        elif scope_type == 'bill_ids':
            bill_ids = scope.get('bill_ids', [])
            if not bill_ids:
                return []
            placeholders = ', '.join(['?' for _ in bill_ids])
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE id IN ({placeholders}) AND {base_condition}",
                tuple(bill_ids),
            )
        else:
            rows = []
        return [r['id'] for r in rows]
