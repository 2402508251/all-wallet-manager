"""AI 基础服务：配置、健康检查与任务记录。"""
import json
import re
from datetime import datetime

from core.dal import DAL
from core.crypto_utils import CredentialEncryptor
from .provider_factory import create_chat_model
from .repository import AIRepository
from .validators import mask_secret, validate_provider_config


class AIService:
    """AI 服务主类，提供配置管理、健康检查和任务记录功能。"""

    def __init__(self, dal: DAL, encryptor: CredentialEncryptor):
        """
        初始化 AI 服务实例。

        Args:
            dal: 数据访问层实例
            encryptor: 凭证加密器实例，用于加密/解密 API Key
        """
        self.dal = dal
        self.encryptor = encryptor
        self.repository = AIRepository(dal)

    def _now(self) -> str:
        """获取当前时间的 ISO 格式字符串（东八区）。"""
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

    def get_config(self) -> dict:
        """
        获取当前 AI Provider 配置。

        Returns:
            dict: 包含 provider_type, model_name, api_base, api_key_masked 等字段的配置字典
        """
        row = self.repository.get_provider_config()
        if not row:
            return {
                'provider_type': 'openai_compatible',
                'model_name': '',
                'api_base': '',
                'api_key_masked': '',
                'has_api_key': False,
                'temperature': 0.2,
                'timeout_seconds': 60,
                'max_tokens': 2048,
                'enabled_tasks': ['category_mapping'],
                'is_enabled': 1,
            }
        enabled_tasks = AIRepository._json_loads(row.get('enabled_tasks'), [])
        return {
            'id': row.get('id'),
            'provider_type': row.get('provider_type'),
            'model_name': row.get('model_name'),
            'api_base': row.get('api_base') or '',
            'api_key_masked': '****' if row.get('api_key_enc') else '',
            'has_api_key': bool(row.get('api_key_enc')),
            'temperature': row.get('temperature'),
            'timeout_seconds': row.get('timeout_seconds'),
            'max_tokens': row.get('max_tokens'),
            'enabled_tasks': enabled_tasks,
            'is_enabled': row.get('is_enabled'),
            'created_at': row.get('created_at'),
            'updated_at': row.get('updated_at'),
        }

    def save_config(self, data: dict) -> dict:
        """
        保存 AI Provider 配置。

        Args:
            data: 配置数据字典，包含 provider_type, model_name, api_key 等字段

        Returns:
            dict: 保存后的配置信息，包含 id 和 api_key_masked

        Raises:
            ValueError: 配置验证失败时抛出
        """
        normalized = validate_provider_config(data)
        current = self.repository.get_provider_config()
        api_key = str(data.get('api_key') or '').strip()
        if api_key:
            normalized['api_key_enc'] = self.encryptor.encrypt(api_key)
        elif current:
            normalized['api_key_enc'] = current.get('api_key_enc')
        else:
            normalized['api_key_enc'] = ''
        normalized['updated_at'] = self._now()
        normalized['created_at'] = self._now()
        config_id = self.repository.save_provider_config(normalized)
        result = self.get_config()
        result['id'] = config_id
        if api_key:
            result['api_key_masked'] = mask_secret(api_key)
        return result

    def _load_runtime_config(self) -> tuple[dict, str]:
        """
        加载运行时配置并解密 API Key。

        Returns:
            tuple[dict, str]: (配置字典, 解密后的 API Key)

        Raises:
            ValueError: 配置未启用时抛出
        """
        config = self.repository.get_provider_config()
        if not config or not config.get('is_enabled'):
            raise ValueError('请先启用 AI 配置')
        api_key = ''
        if config.get('api_key_enc'):
            api_key = self.encryptor.decrypt(config['api_key_enc'])
        return config, api_key

    def health_check(self) -> dict:
        """
        执行 AI 服务健康检查。

        通过调用 LLM 发送测试请求来验证服务可用性。

        Returns:
            dict: 包含 task_id, success, provider, model_name, response_preview 的结果

        Raises:
            ValueError: 配置未启用时抛出
            Exception: LLM 调用失败时抛出
        """
        config, api_key = self._load_runtime_config()
        task_id = self.repository.create_task(
            'health_check',
            input_payload={'prompt': 'ping'},
            provider=config.get('provider_type'),
            model_name=config.get('model_name'),
            status='running',
        )
        try:
            model = create_chat_model(config, api_key)
            response = model.invoke('请只回复 JSON：{"ok": true}')
            content = getattr(response, 'content', response)
            payload = {'response': str(content)[:1000]}
            self.repository.update_task(
                task_id,
                status='success',
                result_payload_json=payload,
                error_message='',
                updated_at=self._now(),
            )
            return {
                'task_id': task_id,
                'success': True,
                'provider': config.get('provider_type'),
                'model_name': config.get('model_name'),
                'response_preview': payload['response'],
            }
        except Exception as exc:
            self.repository.update_task(
                task_id,
                status='failed',
                result_payload_json={},
                error_message=str(exc),
                updated_at=self._now(),
            )
            raise

    def invoke_json(self, system_prompt: str, user_payload: dict) -> dict:
        """调用 LLM 并解析 JSON 响应。"""
        config, api_key = self._load_runtime_config()
        model = create_chat_model(config, api_key)
        prompt = (
            f"{system_prompt}\n\n"
            "请严格输出一个 JSON 对象，不要输出 Markdown、代码块或额外说明。\n"
            f"输入数据：\n{json.dumps(user_payload, ensure_ascii=False, default=str)}"
        )
        response = model.invoke(prompt)
        content = str(getattr(response, 'content', response) or '').strip()
        if content.startswith('```'):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            match = re.search(r"\{.*\}", content, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            preview = content[:300].replace('\n', ' ')
            raise ValueError(f'模型返回内容不是合法 JSON（响应预览：{preview}）') from exc

    def create_mock_task(self, task_type: str = 'mock') -> dict:
        """
        创建模拟任务（用于测试 AI 基础设施是否就绪）。

        Args:
            task_type: 任务类型，默认为 'mock'

        Returns:
            dict: 包含 task_id 的结果
        """
        config = self.repository.get_provider_config() or {}
        task_id = self.repository.create_task(
            task_type,
            input_payload={'source': 'phase0'},
            provider=config.get('provider_type', ''),
            model_name=config.get('model_name', ''),
            status='success',
        )
        self.repository.update_task(
            task_id,
            result_payload_json={'message': 'AI 基础设施已就绪'},
            updated_at=self._now(),
        )
        return {'task_id': task_id}

    def list_tasks(self, task_type: str | None = None, limit: int = 20) -> list[dict]:
        """
        查询 AI 任务列表。

        Args:
            task_type: 可选的任务类型过滤
            limit: 返回记录数量限制，默认 20 条

        Returns:
            list[dict]: 任务记录列表
        """
        return self.repository.list_tasks(task_type=task_type, limit=limit)