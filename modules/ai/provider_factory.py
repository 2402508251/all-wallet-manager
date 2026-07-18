"""
LangChain Provider 工厂模块。

提供统一的 LLM 模型创建接口，支持多种 AI Provider。
当前主要支持 OpenAI 兼容的 API 接口。
"""


class AIProviderNotConfigured(RuntimeError):
    """AI Provider 未配置异常。当缺少必要的配置（如 API Key）时抛出。"""
    pass


class AIProviderUnavailable(RuntimeError):
    """AI Provider 不可用异常。当 Provider 不支持或依赖缺失时抛出。"""
    pass


def create_chat_model(config: dict, api_key: str):
    """
    创建 LangChain Chat 模型实例。

    根据配置创建对应的 LLM 模型实例，当前仅支持 OpenAI 兼容接口。

    Args:
        config: 配置字典，包含以下字段：
            - provider_type: Provider 类型（默认 'openai_compatible'）
            - model_name: 模型名称
            - api_base: API 基础地址（可选）
            - temperature: 温度参数（默认 0.2）
            - timeout_seconds: 超时时间（默认 60 秒）
            - max_tokens: 最大 token 数（默认 2048）
        api_key: API 密钥

    Returns:
        ChatOpenAI: LangChain ChatOpenAI 实例

    Raises:
        AIProviderUnavailable: Provider 类型不支持或依赖缺失时抛出
        AIProviderNotConfigured: API Key 未配置时抛出
    """
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