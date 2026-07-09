"""AI 基础服务：配置、健康检查与任务记录。"""
from datetime import datetime

from core.dal import DAL
from core.crypto_utils import CredentialEncryptor
from .provider_factory import create_chat_model
from .repository import AIRepository
from .validators import mask_secret, validate_provider_config


class AIService:
    def __init__(self, dal: DAL, encryptor: CredentialEncryptor):
        self.dal = dal
        self.encryptor = encryptor
        self.repository = AIRepository(dal)

    def _now(self) -> str:
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

    def get_config(self) -> dict:
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
        config = self.repository.get_provider_config()
        if not config or not config.get('is_enabled'):
            raise ValueError('请先启用 AI 配置')
        api_key = ''
        if config.get('api_key_enc'):
            api_key = self.encryptor.decrypt(config['api_key_enc'])
        return config, api_key

    def health_check(self) -> dict:
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

    def create_mock_task(self, task_type: str = 'mock') -> dict:
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
        return self.repository.list_tasks(task_type=task_type, limit=limit)
