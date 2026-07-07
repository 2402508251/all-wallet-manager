"""分类引擎数据结构。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CategoryRule:
    id: int
    category_id: int
    keyword: str
    match_field: str
    weight: int = 10
    priority: int = 0
    match_mode: str = 'contains'
    category_sort_order: int = 0


@dataclass
class RuleHit:
    rule_id: int
    category_id: int
    keyword: str
    match_field: str
    weight: int
    priority: int


@dataclass
class CategoryResult:
    matched: bool
    category_id: Optional[int] = None
    score: int = 0
    rule_id: Optional[int] = None
    hits: list[RuleHit] = field(default_factory=list)


@dataclass
class MatchContext:
    bill_id: int
    self_fields: dict
    initiator_fields: dict
    meta: dict
