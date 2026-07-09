"""ApiBridge domain mixin."""
import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta

from core.db_rebuild import rebuild_database
from core.trade_types import VALID_TRADE_TYPES, TRADE_TYPE_LABELS, get_trade_type_label
from modules.accounting.credit_tracker import CreditTracker
from modules.accounting.cross_platform_merger import CrossPlatformMerger
from modules.accounting.transfer_pairer import TransferPairer

from .bridge_base import DateTimeEncoder, audit_log, logger


class AiBridgeMixin:
    def _ai_service(self):
        from modules.ai.llm_service import AIService
        return AIService(self.dal, self.encryptor)

    def get_ai_config(self, params=None) -> dict:
        try:
            return self.ok(self._ai_service().get_config())
        except Exception as e:
            logger.exception("get_ai_config failed")
            return self.err(str(e))

    @audit_log('save_ai_config')
    def save_ai_config(self, params=None) -> dict:
        try:
            config = self._ai_service().save_config(params or {})
            return self.ok(config, 'AI 配置已保存')
        except Exception as e:
            logger.exception("save_ai_config failed")
            return self.err(str(e))

    def test_ai_connection(self, params=None) -> dict:
        try:
            result = self._ai_service().health_check()
            return self.ok(result, 'AI 连接测试成功')
        except Exception as e:
            logger.exception("test_ai_connection failed")
            return self.err(str(e))

    def create_ai_mock_task(self, params=None) -> dict:
        try:
            task_type = (params or {}).get('task_type') or 'mock'
            return self.ok(self._ai_service().create_mock_task(task_type))
        except Exception as e:
            logger.exception("create_ai_mock_task failed")
            return self.err(str(e))

    def list_ai_tasks(self, params=None) -> dict:
        try:
            p = params or {}
            tasks = self._ai_service().list_tasks(p.get('task_type'), p.get('limit', 20))
            return self.ok({'list': tasks})
        except Exception as e:
            logger.exception("list_ai_tasks failed")
            return self.err(str(e))
