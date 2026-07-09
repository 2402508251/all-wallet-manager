"""AI 输出与配置校验。"""
import re

SUPPORTED_PROVIDERS = {'openai_compatible'}
SUPPORTED_TASKS = {'parser_rule', 'category_mapping', 'report_generation'}
DANGEROUS_SQL_PATTERN = re.compile(
    r"\b(PRAGMA|ATTACH|DETACH|INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|REPLACE|TRUNCATE|VACUUM|UNION)\b|;",
    re.IGNORECASE,
)


def validate_provider_config(data: dict) -> dict:
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


def mask_secret(value: str | None) -> str:
    if not value:
        return ''
    text = str(value)
    if len(text) <= 8:
        return '****'
    return f"{text[:4]}****{text[-4:]}"


def assert_safe_select_sql(sql: str) -> None:
    text = str(sql or '').strip()
    if not text.lower().startswith('select'):
        raise ValueError('仅允许 SELECT 查询')
    if DANGEROUS_SQL_PATTERN.search(text):
        raise ValueError('SQL 包含不允许的关键字或多语句符号')
