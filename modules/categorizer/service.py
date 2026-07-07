"""分类服务入口。"""
from core.dal import DAL
from .field_resolver import FieldResolver
from .models import CategoryResult
from .rule_repository import CategoryRuleRepository
from .scorer import CategoryScorer


class CategoryService:
    OTHER_EXPENSE_ID = 99
    INCOME_ID = 12
    OTHER_EXPENSE_NAMES = ['其他支出(未命中)', '其他支出']
    INCOME_NAMES = ['收入']

    def __init__(self, dal: DAL):
        self.dal = dal
        self.repository = CategoryRuleRepository(dal)
        self.resolver = FieldResolver(dal)
        self.scorer = CategoryScorer()
        self._rules = None
        self._category_cache = {}

    def list_match_fields(self) -> list[dict]:
        return self.repository.list_match_fields(enabled_only=False)

    def categorize_bill(self, bill_id: int, bill: dict | None = None) -> CategoryResult:
        if bill and not self._should_categorize(bill):
            return CategoryResult(matched=False)
        context = self.resolver.build_context(bill_id, bill=bill)
        if context is None:
            return CategoryResult(matched=False)

        direction = context.meta.get('direction')
        if direction == 'income':
            return self._default_category_result('income')

        rules = self._get_rules()
        result = self.scorer.score(context, rules)
        if result.matched:
            return result
        if direction == 'expense':
            return self._default_category_result('other_expense')
        return result

    def apply_result(self, bill_id: int, result: CategoryResult) -> int:
        if result.matched:
            data = {
                'category_id': result.category_id,
                'category_source': 'auto',
                'category_score': result.score,
                'category_rule_id': result.rule_id,
            }
        else:
            data = {
                'category_id': None,
                'category_source': 'none',
                'category_score': 0,
                'category_rule_id': None,
            }
        return self.dal.update('unified_bills', data, 'id = ?', (bill_id,))

    def _get_rules(self):
        if self._rules is None:
            self._rules = self.repository.list_rules()
        return self._rules

    def _should_categorize(self, bill: dict) -> bool:
        if bill.get('is_deleted') or bill.get('is_system'):
            return False
        if bill.get('is_category_manual_edited'):
            return False
        return bill.get('direction') in ('expense', 'income')

    def _default_category_result(self, category_kind: str) -> CategoryResult:
        category_id = self._get_system_category_id(category_kind)
        if category_id is None:
            return CategoryResult(matched=False)
        return CategoryResult(matched=True, category_id=category_id, score=0, rule_id=None)

    def get_other_expense_category_id(self):
        return self._get_system_category_id('other_expense')

    def _get_system_category_id(self, category_kind: str):
        if category_kind not in self._category_cache:
            if category_kind == 'other_expense':
                category_id = self.OTHER_EXPENSE_ID
                candidate_names = self.OTHER_EXPENSE_NAMES
            elif category_kind == 'income':
                category_id = self.INCOME_ID
                candidate_names = self.INCOME_NAMES
            else:
                return None

            row = self.dal.fetch_one(
                "SELECT id FROM bill_categories WHERE id = ? AND is_enabled = 1 ORDER BY id LIMIT 1",
                (category_id,),
            )
            if not row:
                placeholders = ', '.join(['?' for _ in candidate_names])
                row = self.dal.fetch_one(
                    f"SELECT id FROM bill_categories WHERE name IN ({placeholders}) AND is_enabled = 1 ORDER BY id LIMIT 1",
                    tuple(candidate_names),
                )
            self._category_cache[category_kind] = row['id'] if row else None
        return self._category_cache[category_kind]
