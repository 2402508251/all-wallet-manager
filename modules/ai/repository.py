"""
AI 模块的数据访问层。

封装所有与 AI 配置和任务相关的数据库操作，提供统一的数据访问接口。
"""
import json
from typing import Any

from core.dal import DAL


class AIRepository:
    """AI 数据访问层，处理 AI Provider 配置和任务记录的 CRUD 操作。"""

    def __init__(self, dal: DAL):
        """
        初始化 AI Repository 实例。

        Args:
            dal: 数据访问层实例
        """
        self.dal = dal

    @staticmethod
    def _json_dumps(value: Any) -> str:
        """
        将对象序列化为 JSON 字符串。

        Args:
            value: 需要序列化的对象

        Returns:
            str: JSON 字符串
        """
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)

    @staticmethod
    def _json_loads(value: str | None, default=None):
        """
        从 JSON 字符串反序列化对象。

        Args:
            value: JSON 字符串
            default: 解析失败时的默认返回值

        Returns:
            Any: 反序列化后的对象，失败时返回 default
        """
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def get_provider_config(self) -> dict | None:
        """
        获取最新的 AI Provider 配置。

        Returns:
            dict | None: 配置字典，不存在时返回 None
        """
        row = self.dal.fetch_one(
            """
            SELECT * FROM ai_provider_configs
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else None

    def save_provider_config(self, data: dict) -> int:
        """
        保存 AI Provider 配置（插入或更新）。

        如果已存在配置则更新，否则插入新配置。

        Args:
            data: 配置数据字典

        Returns:
            int: 配置记录 ID
        """
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
        """
        创建 AI 任务记录。

        Args:
            task_type: 任务类型（如 'health_check', 'parser_rule' 等）
            input_payload: 输入数据负载
            context_payload: 上下文数据负载
            provider: Provider 名称
            model_name: 模型名称
            status: 任务状态，默认 'pending'

        Returns:
            int: 任务记录 ID
        """
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
        """
        更新 AI 任务记录。

        Args:
            task_id: 任务 ID
            **fields: 需要更新的字段，支持：
                - status: 任务状态
                - result_payload_json: 结果数据
                - error_message: 错误信息
                - updated_at: 更新时间

        Returns:
            int: 受影响的行数
        """
        payload = {}
        for key, value in fields.items():
            if key in ('input_payload_json', 'context_payload_json', 'result_payload_json'):
                payload[key] = self._json_dumps(value)
            else:
                payload[key] = value
        return self.dal.update('ai_tasks', payload, 'id = ?', (task_id,))

    def list_tasks(self, task_type: str | None = None, limit: int = 20) -> list[dict]:
        """
        查询 AI 任务列表。

        Args:
            task_type: 可选的任务类型过滤
            limit: 返回记录数量限制，范围 1-100，默认 20

        Returns:
            list[dict]: 任务记录列表，已标准化（JSON 字段已解析）
        """
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

    def create_category_suggestion(self, task_id: int, category_id: int, sample_fields: list[dict],
                                   suggestion: dict, confidence: float | None = None,
                                   status: str = 'draft') -> int:
        return self.dal.insert('ai_category_rule_suggestions', {
            'task_id': task_id,
            'target_category_id': category_id,
            'sample_fields_json': self._json_dumps(sample_fields),
            'suggestion_json': self._json_dumps(suggestion),
            'confidence': confidence,
            'status': status,
        })

    def get_category_suggestion(self, suggestion_id: int) -> dict | None:
        row = self.dal.fetch_one(
            """
            SELECT s.*, c.name AS category_name
            FROM ai_category_rule_suggestions s
            LEFT JOIN bill_categories c ON c.id = s.target_category_id
            WHERE s.id = ?
            """,
            (suggestion_id,),
        )
        return self.normalize_category_suggestion(dict(row)) if row else None

    def list_category_suggestions(self, category_id=None, status: str | None = None, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit or 20), 100))
        where = []
        params = []
        if category_id:
            where.append('s.target_category_id = ?')
            params.append(category_id)
        if status:
            where.append('s.status = ?')
            params.append(status)
        where_sql = 'WHERE ' + ' AND '.join(where) if where else ''
        rows = self.dal.fetch_all(
            f"""
            SELECT s.*, c.name AS category_name
            FROM ai_category_rule_suggestions s
            LEFT JOIN bill_categories c ON c.id = s.target_category_id
            {where_sql}
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        )
        return [self.normalize_category_suggestion(dict(row)) for row in rows]

    def update_category_suggestion(self, suggestion_id: int, **fields) -> int:
        payload = {}
        for key, value in fields.items():
            if key in ('sample_fields_json', 'suggestion_json'):
                payload[key] = self._json_dumps(value)
            else:
                payload[key] = value
        return self.dal.update('ai_category_rule_suggestions', payload, 'id = ?', (suggestion_id,))

    def normalize_category_suggestion(self, row: dict) -> dict:
        row['sample_fields'] = self._json_loads(row.pop('sample_fields_json', None), [])
        row['suggestion'] = self._json_loads(row.pop('suggestion_json', None), {})
        return row

    def normalize_task(self, row: dict) -> dict:
        """
        标准化任务记录，将 JSON 字段解析为对象。

        Args:
            row: 原始任务记录字典

        Returns:
            dict: 标准化后的任务记录，包含：
                - input_payload: 输入数据对象
                - context_payload: 上下文数据对象
                - result_payload: 结果数据对象
        """
        row['input_payload'] = self._json_loads(row.pop('input_payload_json', None), {})
        row['context_payload'] = self._json_loads(row.pop('context_payload_json', None), {})
        row['result_payload'] = self._json_loads(row.pop('result_payload_json', None), {})
        return row