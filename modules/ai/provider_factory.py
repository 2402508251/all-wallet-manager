"""LangChain Provider 工厂。"""


class AIProviderNotConfigured(RuntimeError):
    pass


class AIProviderUnavailable(RuntimeError):
    pass


def create_chat_model(config: dict, api_key: str):
    provider_type = config.get('provider_type') or 'openai_compatible'
    if provider_type != 'openai_compatible':
        raise AIProviderUnavailable('暂不支持该 AI Provider 类型')
    if not api_key:
        raise AIProviderNotConfigured('请先配置 API Key')

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise AIProviderUnavailable('缺少 langchain-openai 依赖，请先安装 requirements.txt') from exc

    kwargs = {
        'model': config.get('model_name'),
        'api_key': api_key,
        'temperature': float(config.get('temperature', 0.2)),
        'timeout': int(config.get('timeout_seconds', 60)),
        'max_tokens': int(config.get('max_tokens', 2048)),
    }
    api_base = config.get('api_base')
    if api_base:
        kwargs['base_url'] = api_base
    return ChatOpenAI(**kwargs)
