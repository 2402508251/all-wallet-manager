"""AI 模块的数据访问封装。"""
import json
from typing import Any

from core.dal import DAL


class AIRepository:
    def __init__(self, dal: DAL):
        self.dal = dal

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)

    @staticmethod
    def _json_loads(value: str | None, default=None):
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def get_provider_config(self) -> dict | None:
        row = self.dal.fetch_one(
            """
            SELECT * FROM ai_provider_configs
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else None

    def save_provider_config(self, data: dict) -> int:
        current = self.get_provider_config()
        payload = {
            'provider_type': data.get('provider_type') or 'openai_compatible',
            'model_name': data.get('model_name') or '',
            'api_base': data.get('api_base') or '',
            'temperature': float(data.get('temperature', 0.2)),
            'timeout_seconds': int(data.get('timeout_seconds', 60)),
            'max_tokens': int(data.get('max_tokens', 2048)),
            'enabled_tasks': self._json_dumps(data.get('enabled_tasks') or []),
            'is_enabled': int(data.get('is_enabled', 1)),
            'updated_at': data.get('updated_at'),
        }
        if data.get('api_key_enc') is not None:
            payload['api_key_enc'] = data.get('api_key_enc')

        if current:
            config_id = current['id']
            self.dal.update('ai_provider_configs', payload, 'id = ?', (config_id,))
            return config_id
        payload['created_at'] = data.get('created_at')
        return self.dal.insert('ai_provider_configs', payload)

    def create_task(self, task_type: str, input_payload=None, context_payload=None,
                    provider: str = '', model_name: str = '', status: str = 'pending') -> int:
        return self.dal.insert('ai_tasks', {
            'task_type': task_type,
            'status': status,
            'input_payload_json': self._json_dumps(input_payload or {}),
            'context_payload_json': self._json_dumps(context_payload or {}),
            'result_payload_json': self._json_dumps({}),
            'error_message': '',
            'provider': provider or '',
            'model_name': model_name or '',
        })

    def update_task(self, task_id: int, **fields) -> int:
        payload = {}
        for key, value in fields.items():
            if key in ('input_payload_json', 'context_payload_json', 'result_payload_json'):
                payload[key] = self._json_dumps(value)
            else:
                payload[key] = value
        return self.dal.update('ai_tasks', payload, 'id = ?', (task_id,))

    def list_tasks(self, task_type: str | None = None, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit or 20), 100))
        if task_type:
            rows = self.dal.fetch_all(
                "SELECT * FROM ai_tasks WHERE task_type = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (task_type, limit),
            )
        else:
            rows = self.dal.fetch_all(
                "SELECT * FROM ai_tasks ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            )
        return [self.normalize_task(dict(row)) for row in rows]

    def normalize_task(self, row: dict) -> dict:
        row['input_payload'] = self._json_loads(row.pop('input_payload_json', None), {})
        row['context_payload'] = self._json_loads(row.pop('context_payload_json', None), {})
        row['result_payload'] = self._json_loads(row.pop('result_payload_json', None), {})
        return row
