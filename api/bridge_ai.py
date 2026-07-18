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

    def _category_suggestion_service(self):
        from modules.ai.category_suggestion_service import CategorySuggestionService
        return CategorySuggestionService(self.dal, self.encryptor)

    def generate_category_rule_suggestion(self, params=None) -> dict:
        try:
            data = self._category_suggestion_service().generate_suggestion(params or {})
            return self.ok(data, 'AI 分类关键词建议已生成')
        except Exception as e:
            logger.exception("generate_category_rule_suggestion failed")
            return self.err(str(e))

    def list_category_rule_suggestions(self, params=None) -> dict:
        try:
            data = self._category_suggestion_service().list_suggestions(params or {})
            return self.ok(data)
        except Exception as e:
            logger.exception("list_category_rule_suggestions failed")
            return self.err(str(e))

    @audit_log('approve_category_rule_suggestion')
    def approve_category_rule_suggestion(self, params=None) -> dict:
        try:
            data = self._category_suggestion_service().approve_suggestion(params or {})
            return self.ok(data, 'AI 分类关键词建议已应用')
        except Exception as e:
            logger.exception("approve_category_rule_suggestion failed")
            return self.err(str(e))

    def reject_category_rule_suggestion(self, params=None) -> dict:
        try:
            data = self._category_suggestion_service().reject_suggestion(params or {})
            return self.ok(data, 'AI 分类关键词建议已拒绝')
        except Exception as e:
            logger.exception("reject_category_rule_suggestion failed")
            return self.err(str(e))
