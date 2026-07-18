"""
AI 模块验证器。

提供配置验证、敏感信息脱敏和 SQL 安全检查功能。
"""
import re

SUPPORTED_PROVIDERS = {'openai_compatible'}
"""支持的 AI Provider 类型集合。"""

SUPPORTED_TASKS = {'parser_rule', 'category_mapping', 'report_generation'}
"""支持的 AI 任务类型集合。"""

DANGEROUS_SQL_PATTERN = re.compile(
    r"\b(PRAGMA|ATTACH|DETACH|INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|REPLACE|TRUNCATE|VACUUM|UNION)\b|;",
    re.IGNORECASE,
)
"""危险 SQL 关键字正则模式，用于检测潜在的 SQL 注入。"""

BROAD_CATEGORY_KEYWORDS = {
    '支付', '消费', '付款', '订单', '商户', '转账', '微信', '支付宝', '银行卡', '有限公司'
}
"""过泛关键词集合，避免 AI 建议误伤大量账单。"""


def validate_provider_config(data: dict) -> dict:
    """
    验证并标准化 AI Provider 配置。

    检查配置的各项参数是否符合要求，并返回标准化后的配置字典。

    Args:
        data: 原始配置数据字典，包含以下字段：
            - provider_type: Provider 类型
            - model_name: 模型名称
            - api_base: API 基础地址
            - api_key: API 密钥
            - temperature: 温度参数（0-2）
            - timeout_seconds: 超时时间（5-300秒）
            - max_tokens: 最大 token 数（256-32000）
            - enabled_tasks: 启用的任务列表
            - is_enabled: 是否启用

    Returns:
        dict: 标准化后的配置字典

    Raises:
        ValueError: 配置参数不符合要求时抛出
    """
    provider_type = str(data.get('provider_type') or 'openai_compatible').strip()
    if provider_type not in SUPPORTED_PROVIDERS:
        raise ValueError('暂不支持该 AI Provider 类型')

    model_name = str(data.get('model_name') or '').strip()
    if not model_name:
        raise ValueError('模型名称不能为空')

    api_base = str(data.get('api_base') or '').strip()
    if api_base and not (api_base.startswith('http://') or api_base.startswith('https://')):
        raise ValueError('API 地址必须以 http:// 或 https:// 开头')

    temperature = float(data.get('temperature', 0.2))
    if temperature < 0 or temperature > 2:
        raise ValueError('temperature 必须在 0 到 2 之间')

    timeout_seconds = int(data.get('timeout_seconds', 60))
    if timeout_seconds < 5 or timeout_seconds > 300:
        raise ValueError('超时时间必须在 5 到 300 秒之间')

    max_tokens = int(data.get('max_tokens', 2048))
    if max_tokens < 256 or max_tokens > 32000:
        raise ValueError('max_tokens 必须在 256 到 32000 之间')

    enabled_tasks = data.get('enabled_tasks') or []
    if not isinstance(enabled_tasks, list):
        raise ValueError('启用任务必须是数组')
    invalid = [task for task in enabled_tasks if task not in SUPPORTED_TASKS]
    if invalid:
        raise ValueError(f"不支持的任务类型: {', '.join(invalid)}")

    return {
        'provider_type': provider_type,
        'model_name': model_name,
        'api_base': api_base,
        'temperature': temperature,
        'timeout_seconds': timeout_seconds,
        'max_tokens': max_tokens,
        'enabled_tasks': enabled_tasks,
        'is_enabled': 1 if data.get('is_enabled', 1) else 0,
    }


def validate_category_suggestions(data: dict, allowed_fields: set[str], conflict_lookup: dict[str, list[dict]] | None = None) -> dict:
    """
    校验并标准化 AI 分类关键词建议。

    Args:
        data: 模型返回的 JSON 对象
        allowed_fields: 允许的匹配字段集合
        conflict_lookup: keyword -> 已存在规则列表，用于标记重复/跨分类冲突

    Returns:
        dict: {'summary': str, 'items': list[dict]}
    """
    if not isinstance(data, dict):
        raise ValueError('AI 返回结果必须是对象')
    suggestions = data.get('suggestions')
    if not isinstance(suggestions, list):
        raise ValueError('AI 返回结果缺少 suggestions 数组')

    conflict_lookup = conflict_lookup or {}
    items = []
    seen = set()
    for raw in suggestions[:20]:
        if not isinstance(raw, dict):
            continue
        keyword = str(raw.get('keyword') or '').strip()
        if len(keyword) < 2 or len(keyword) > 40:
            continue
        if keyword.isdigit() or keyword in BROAD_CATEGORY_KEYWORDS:
            continue

        match_field = str(raw.get('match_field') or 'all_text').strip()
        if match_field not in allowed_fields:
            continue

        key = (keyword, match_field)
        if key in seen:
            continue
        seen.add(key)

        weight = _clamp_int(raw.get('weight', 10), 1, 100, 10)
        priority = _clamp_int(raw.get('priority', 0), 0, 100, 0)
        confidence = _clamp_float(raw.get('confidence', 0.5), 0, 1, 0.5)
        conflicts = conflict_lookup.get(keyword, [])
        same_category = [c for c in conflicts if c.get('match_field') == match_field and c.get('same_category')]
        cross_category = [c for c in conflicts if not c.get('same_category')]
        duplicate = bool(same_category)
        if duplicate:
            conflict_level = 'duplicate'
        elif cross_category:
            conflict_level = 'cross_category'
        else:
            conflict_level = 'none'

        items.append({
            'keyword': keyword,
            'match_field': match_field,
            'weight': weight,
            'priority': priority,
            'match_mode': 'contains',
            'reason': str(raw.get('reason') or '').strip()[:300],
            'confidence': confidence,
            'duplicate': duplicate,
            'conflict_level': conflict_level,
            'conflict_categories': cross_category,
        })

    if not items:
        raise ValueError('AI 未返回可用的关键词建议')
    return {
        'summary': str(data.get('summary') or f'生成 {len(items)} 条关键词建议')[:300],
        'items': items,
    }


def _clamp_int(value, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _clamp_float(value, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def mask_secret(value: str | None) -> str:
    """
    对敏感信息进行脱敏处理。

    保留前 4 位和后 4 位，中间用 **** 替代。

    Args:
        value: 需要脱敏的字符串

    Returns:
        str: 脱敏后的字符串，如 'sk-****1234'

    Examples:
        >>> mask_secret('sk-abcdefghijklmnopqrstuvwxyz')
        'sk-a****wxyz'
        >>> mask_secret('short')
        '****'
    """
    if not value:
        return ''
    text = str(value)
    if len(text) <= 8:
        return '****'
    return f"{text[:4]}****{text[-4:]}"


def assert_safe_select_sql(sql: str) -> None:
    """
    验证 SQL 查询语句的安全性。

    确保只允许 SELECT 查询，且不包含危险的关键字或多语句。

    Args:
        sql: SQL 查询语句

    Raises:
        ValueError: SQL 不是 SELECT 查询或包含危险关键字时抛出

    Examples:
        >>> assert_safe_select_sql('SELECT * FROM users')  # OK
        >>> assert_safe_select_sql('DROP TABLE users')  # Raises ValueError
    """
    text = str(sql or '').strip()
    if not text.lower().startswith('select'):
        raise ValueError('仅允许 SELECT 查询')
    if DANGEROUS_SQL_PATTERN.search(text):
        raise ValueError('SQL 包含不允许的关键字或多语句符号')