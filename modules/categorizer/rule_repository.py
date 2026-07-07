"""分类规则读取。"""
from core.dal import DAL
from .models import CategoryRule


class CategoryRuleRepository:
    def __init__(self, dal: DAL):
        self.dal = dal

    def list_match_fields(self, enabled_only: bool = True) -> list[dict]:
        where = "WHERE is_enabled = 1" if enabled_only else ""
        rows = self.dal.fetch_all(
            f"SELECT * FROM category_match_fields {where} ORDER BY sort_order, field_key"
        )
        return [dict(r) for r in rows]

    def list_rules(self) -> list[CategoryRule]:
        rows = self.dal.fetch_all(
            """
            SELECT ck.*, bc.sort_order AS category_sort_order
            FROM category_keywords ck
            JOIN bill_categories bc ON bc.id = ck.category_id
            LEFT JOIN category_match_fields cmf ON cmf.field_key = ck.match_field
            WHERE ck.is_enabled = 1
              AND bc.is_enabled = 1
              AND (cmf.field_key IS NULL OR cmf.is_enabled = 1)
            ORDER BY ck.priority DESC, ck.weight DESC, ck.id ASC
            """
        )
        return [
            CategoryRule(
                id=r['id'],
                category_id=r['category_id'],
                keyword=r.get('keyword') or '',
                match_field=r.get('match_field') or 'counterparty',
                weight=r.get('weight') or 10,
                priority=r.get('priority') or 0,
                match_mode=r.get('match_mode') or 'contains',
                category_sort_order=r.get('category_sort_order') or 0,
            )
            for r in rows
            if (r.get('keyword') or '').strip()
        ]
