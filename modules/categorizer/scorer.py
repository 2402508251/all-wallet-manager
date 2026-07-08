"""分类规则打分。"""
from collections import defaultdict
from .models import CategoryResult, CategoryRule, MatchContext, RuleHit


def _norm(value: str) -> str:
    return str(value or '').strip().lower()


class CategoryScorer:
    def score(self, context: MatchContext, rules: list[CategoryRule]) -> CategoryResult:
        scores: dict[int, int] = defaultdict(int)
        hits_by_category: dict[int, list[RuleHit]] = defaultdict(list)

        for rule in rules:
            target = self._field_value(context, rule.match_field)
            if not target or not self._matches(target, rule):
                continue
            hit = RuleHit(
                rule_id=rule.id,
                category_id=rule.category_id,
                keyword=rule.keyword,
                match_field=rule.match_field,
                weight=rule.weight,
                priority=rule.priority,
            )
            scores[rule.category_id] += rule.weight
            hits_by_category[rule.category_id].append(hit)

        if not scores:
            return CategoryResult(matched=False)

        def sort_key(category_id: int):
            hits = hits_by_category[category_id]
            max_weight = max(h.weight for h in hits)
            priority_sum = sum(h.priority for h in hits)
            sort_order = self._category_sort_order(category_id, rules)
            return (scores[category_id], max_weight, len(hits), priority_sum, -sort_order)

        category_id = max(scores.keys(), key=sort_key)
        hits = hits_by_category[category_id]
        deciding = max(hits, key=lambda h: (h.weight, h.priority, -h.rule_id))
        return CategoryResult(
            matched=True,
            category_id=category_id,
            score=scores[category_id],
            rule_id=deciding.rule_id,
            hits=hits,
        )

    def _field_value(self, context: MatchContext, match_field: str) -> str:
        if match_field.startswith('initiator_'):
            key = match_field.replace('initiator_', '', 1)
            return context.initiator_fields.get(key, '')
        return self._merged_field_value(context, match_field)

    def _merged_field_value(self, context: MatchContext, match_field: str) -> str:
        values = []
        self_value = context.self_fields.get(match_field, '')
        initiator_value = context.initiator_fields.get(match_field, '')
        if self_value:
            values.append(self_value)
        if initiator_value and initiator_value not in values:
            values.append(initiator_value)
        return ' '.join(values)

    def _matches(self, target: str, rule: CategoryRule) -> bool:
        target_norm = _norm(target)
        keyword = _norm(rule.keyword)
        if not keyword:
            return False
        if rule.match_mode == 'equals':
            return target_norm == keyword
        if rule.match_mode == 'prefix':
            return target_norm.startswith(keyword)
        return keyword in target_norm

    def _category_sort_order(self, category_id: int, rules: list[CategoryRule]) -> int:
        for rule in rules:
            if rule.category_id == category_id:
                return rule.category_sort_order
        return 0
