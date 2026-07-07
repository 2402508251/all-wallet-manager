"""分类匹配上下文构建。"""
from core.dal import DAL
from .models import MatchContext


TEXT_FIELDS = ('counterparty', 'product_desc', 'remark')


def _text(value) -> str:
    return str(value or '').strip()


def _field_map(row: dict | None) -> dict:
    row = row or {}
    data = {name: _text(row.get(name)) for name in TEXT_FIELDS}
    data['all_text'] = ' '.join(v for v in data.values() if v)
    return data


class FieldResolver:
    def __init__(self, dal: DAL):
        self.dal = dal

    def build_context(self, bill_id: int, bill: dict | None = None) -> MatchContext | None:
        bill = bill or self.dal.fetch_one(
            "SELECT * FROM unified_bills WHERE id = ?",
            (bill_id,),
        )
        if not bill:
            return None

        accounting = self.dal.fetch_one(
            "SELECT * FROM bill_accounting WHERE bill_id = ?",
            (bill_id,),
        ) or {}
        initiator = self._find_initiator(bill, accounting)

        return MatchContext(
            bill_id=bill_id,
            self_fields=_field_map(bill),
            initiator_fields=_field_map(initiator),
            meta={
                'channel': bill.get('channel'),
                'trade_type': bill.get('trade_type'),
                'direction': bill.get('direction'),
                'merge_status': accounting.get('merge_status'),
                'merged_group_id': accounting.get('merged_group_id'),
            },
        )

    def _find_initiator(self, bill: dict, accounting: dict) -> dict | None:
        merge_status = accounting.get('merge_status')
        if merge_status != 'merged_target':
            return None

        group_id = accounting.get('merged_group_id')
        if not group_id:
            return None

        return self.dal.fetch_one(
            """
            SELECT ub.*
            FROM unified_bills ub
            JOIN bill_accounting ba ON ba.bill_id = ub.id
            WHERE ba.merged_group_id = ?
              AND ba.merge_status = 'merged_source'
              AND ub.is_deleted = 0
            ORDER BY ub.id ASC
            LIMIT 1
            """,
            (group_id,),
        )
