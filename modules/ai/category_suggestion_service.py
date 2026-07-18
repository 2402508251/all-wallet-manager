"""
AI 分类关键词建议服务。

提供基于 AI 的账单分类关键词建议生成、审核和应用功能。
通过分析账单样本，利用 LLM 生成关键词匹配规则，帮助用户快速建立分类规则。
"""
from datetime import datetime

from core.crypto_utils import CredentialEncryptor
from core.dal import DAL
from modules.categorizer import CategoryService
from .llm_service import AIService
from .repository import AIRepository
from .validators import validate_category_suggestions


class CategorySuggestionService:
    """
    分类关键词建议服务。

    负责：
    - 根据账单样本生成分类关键词建议
    - 管理建议的审核流程（批准/拒绝）
    - 将批准的建议应用到分类规则中
    """

    def __init__(self, dal: DAL, encryptor: CredentialEncryptor):
        """
        初始化分类建议服务实例。

        Args:
            dal: 数据访问层实例
            encryptor: 凭证加密器实例，用于解密 API Key
        """
        self.dal = dal
        self.encryptor = encryptor
        self.ai_service = AIService(dal, encryptor)
        self.repository = AIRepository(dal)
        self.category_service = CategoryService(dal)

    def _now(self) -> str:
        """获取当前时间的 ISO 格式字符串（东八区）。"""
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

    def generate_suggestion(self, params: dict) -> dict:
        """
        生成分类关键词建议。

        根据提供的账单样本，调用 LLM 生成关键词匹配规则建议。

        Args:
            params: 参数字典，包含：
                - category_id: 目标分类 ID
                - sample_mode: 样本来源模式
                    - 'manual': 手动提供的样本
                    - 'uncategorized_recent': 最近的未分类账单
                    - 'selected_bills': 指定的账单 ID 列表
                - limit: 样本数量限制（默认 20，最大 30）
                - manual_samples: 手动提供的样本列表（sample_mode='manual' 时）
                - bill_ids: 账单 ID 列表（sample_mode='selected_bills' 时）

        Returns:
            dict: 包含以下字段的建议结果：
                - task_id: 任务 ID
                - suggestion_id: 建议记录 ID
                - category: 目标分类信息
                - summary: AI 生成的建议摘要
                - suggestions: 关键词建议列表

        Raises:
            ValueError: 样本为空或参数无效时抛出
            Exception: LLM 调用失败时抛出
        """
        category_id = params.get('category_id')
        category = self._get_category(category_id)
        samples = self._collect_samples(params)
        if not samples:
            raise ValueError('样本为空，无法生成建议')

        fields = self.category_service.list_match_fields()
        allowed_fields = {f['field_key'] for f in fields if f.get('is_enabled', 1)}
        existing_keywords = self._list_existing_keywords(category_id)
        conflict_lookup = self._build_conflict_lookup(category_id)
        runtime_config = self.repository.get_provider_config() or {}
        task_id = self.repository.create_task(
            'category_mapping',
            input_payload={
                'category_id': category_id,
                'sample_mode': params.get('sample_mode') or 'manual',
                'sample_count': len(samples),
            },
            context_payload={
                'category': category,
                'allowed_fields': fields,
                'samples': samples,
            },
            provider=runtime_config.get('provider_type', ''),
            model_name=runtime_config.get('model_name', ''),
            status='running',
        )

        try:
            payload = {
                'target_category': category,
                'allowed_match_fields': fields,
                'existing_keywords': existing_keywords,
                'samples': samples,
            }
            raw = self.ai_service.invoke_json(self._system_prompt(), payload)
            try:
                suggestion = validate_category_suggestions(raw, allowed_fields, conflict_lookup)
            except ValueError as exc:
                diagnostic = self._response_diagnostic(raw)
                raise ValueError(f'{exc}（{diagnostic}）') from exc
            confidence = self._avg_confidence(suggestion['items'])
            with self.dal.transaction():
                suggestion_id = self.repository.create_category_suggestion(
                    task_id,
                    category_id,
                    samples,
                    suggestion,
                    confidence=confidence,
                )
                self.repository.update_task(
                    task_id,
                    status='success',
                    result_payload_json={'suggestion_id': suggestion_id, **suggestion},
                    error_message='',
                    updated_at=self._now(),
                )
            return {
                'task_id': task_id,
                'suggestion_id': suggestion_id,
                'category': category,
                'summary': suggestion['summary'],
                'suggestions': suggestion['items'],
            }
        except Exception as exc:
            self.repository.update_task(
                task_id,
                status='failed',
                error_message=str(exc),
                updated_at=self._now(),
            )
            raise

    def list_suggestions(self, params: dict) -> dict:
        """
        查询分类关键词建议列表。

        Args:
            params: 查询参数字典，包含：
                - category_id: 可选，分类 ID 过滤
                - status: 可选，状态过滤（'draft', 'applied', 'rejected'）
                - limit: 返回数量限制，默认 20

        Returns:
            dict: 包含 'list' 字段的字典，值为建议记录列表
        """
        rows = self.repository.list_category_suggestions(
            category_id=params.get('category_id'),
            status=params.get('status'),
            limit=params.get('limit', 20),
        )
        return {'list': rows}

    def approve_suggestion(self, params: dict) -> dict:
        """
        批准并应用分类关键词建议。

        将选中的建议项添加到分类关键词规则中，并更新建议状态为 'applied'。

        Args:
            params: 参数字典，包含：
                - suggestion_id: 建议 ID
                - selected_items: 选中的建议项列表，每项包含：
                    - keyword: 关键词
                    - match_field: 匹配字段
                    - weight: 权重（1-100）
                    - priority: 优先级（0-100）
                - reviewer_note: 可选，审核备注

        Returns:
            dict: 应用结果，包含：
                - inserted_count: 成功插入的数量
                - skipped_count: 跳过的数量
                - inserted: 成功插入的规则列表
                - skipped: 跳过的规则列表（含原因）

        Raises:
            ValueError: 建议不存在、已处理或选中的项均不可应用时抛出
        """
        suggestion_id = params.get('suggestion_id')
        selected_items = params.get('selected_items') or []
        if not selected_items:
            raise ValueError('未选择要应用的建议')

        inserted = []
        skipped = []
        now = self._now()
        with self.dal.transaction():
            suggestion = self.repository.get_category_suggestion(suggestion_id)
            if not suggestion:
                raise ValueError('建议不存在')
            if suggestion.get('status') != 'draft':
                raise ValueError('该建议已处理，不能重复应用')
            category_id = suggestion['target_category_id']
            allowed_fields = {f['field_key'] for f in self.category_service.list_match_fields() if f.get('is_enabled', 1)}
            suggestion_items = suggestion.get('suggestion', {}).get('items', [])
            allowed_keys = {(i.get('keyword'), i.get('match_field')) for i in suggestion_items}

            allow_cross_category_conflicts = bool(params.get('allow_cross_category_conflicts', False))
            for raw in selected_items:
                item = self._normalize_apply_item(raw, allowed_fields)
                if (item['keyword'], item['match_field']) not in allowed_keys:
                    skipped.append({'keyword': item['keyword'], 'reason': '不在原始建议中'})
                    continue
                exists = self.dal.fetch_one(
                    """
                    SELECT id FROM category_keywords
                    WHERE category_id = ? AND keyword = ? AND match_field = ? AND match_mode = ?
                    LIMIT 1
                    """,
                    (category_id, item['keyword'], item['match_field'], 'contains'),
                )
                if exists:
                    skipped.append({'keyword': item['keyword'], 'reason': '规则已存在'})
                    continue
                cross_conflicts = self.dal.fetch_all(
                    """
                    SELECT bc.name AS category_name, ck.match_field
                    FROM category_keywords ck
                    JOIN bill_categories bc ON bc.id = ck.category_id
                    WHERE ck.keyword = ? AND ck.category_id != ? AND ck.is_enabled = 1
                    ORDER BY bc.name, ck.match_field
                    """,
                    (item['keyword'], category_id),
                )
                if cross_conflicts and not allow_cross_category_conflicts:
                    category_names = '、'.join(sorted({row['category_name'] for row in cross_conflicts}))
                    skipped.append({'keyword': item['keyword'], 'reason': f'存在跨分类冲突：{category_names}'})
                    continue
                row_id = self.dal.insert('category_keywords', {
                    'category_id': category_id,
                    'keyword': item['keyword'],
                    'match_field': item['match_field'],
                    'weight': item['weight'],
                    'priority': item['priority'],
                    'match_mode': 'contains',
                    'is_enabled': 1,
                    'source': 'ai',
                    'created_at': now,
                    'updated_at': now,
                })
                inserted.append({**item, 'id': row_id})

            if not inserted:
                conflict_reasons = [item['reason'] for item in skipped if '跨分类冲突' in item.get('reason', '')]
                if conflict_reasons:
                    raise ValueError('选中的建议存在跨分类冲突，请确认后再应用')
                raise ValueError('选中的建议均已存在或不可应用')
            self.repository.update_category_suggestion(
                suggestion_id,
                status='applied',
                reviewer_note=params.get('reviewer_note') or '',
                updated_at=now,
            )
            self.repository.update_task(
                suggestion['task_id'],
                status='applied',
                updated_at=now,
            )

        return {
            'inserted_count': len(inserted),
            'skipped_count': len(skipped),
            'inserted': inserted,
            'skipped': skipped,
        }

    def reject_suggestion(self, params: dict) -> dict:
        """
        拒绝分类关键词建议。

        将建议状态更新为 'rejected'，不会应用任何规则。

        Args:
            params: 参数字典，包含：
                - suggestion_id: 建议 ID
                - reviewer_note: 可选，审核备注

        Returns:
            dict: 包含 suggestion_id 和 status 的结果字典

        Raises:
            ValueError: 建议不存在或已处理时抛出
        """
        suggestion_id = params.get('suggestion_id')
        suggestion = self.repository.get_category_suggestion(suggestion_id)
        if not suggestion:
            raise ValueError('建议不存在')
        if suggestion.get('status') != 'draft':
            raise ValueError('该建议已处理')
        now = self._now()
        with self.dal.transaction():
            self.repository.update_category_suggestion(
                suggestion_id,
                status='rejected',
                reviewer_note=params.get('reviewer_note') or '',
                updated_at=now,
            )
            self.repository.update_task(suggestion['task_id'], status='rejected', updated_at=now)
        return {'suggestion_id': suggestion_id, 'status': 'rejected'}

    def _get_category(self, category_id) -> dict:
        """
        获取分类信息。

        Args:
            category_id: 分类 ID

        Returns:
            dict: 包含 id 和 name 的分类信息字典

        Raises:
            ValueError: 分类不存在或已禁用时抛出
        """
        row = self.dal.fetch_one(
            "SELECT id, name FROM bill_categories WHERE id = ? AND is_enabled = 1",
            (category_id,),
        )
        if not row:
            raise ValueError('分类不存在或已禁用')
        return dict(row)

    def _collect_samples(self, params: dict) -> list[dict]:
        """
        收集账单样本。

        根据不同的样本来源模式收集账单数据。

        Args:
            params: 参数字典，包含样本来源配置

        Returns:
            list[dict]: 账单样本列表，每个样本已清洗和标准化

        Raises:
            ValueError: 不支持的样本来源模式时抛出
        """
        mode = params.get('sample_mode') or 'manual'
        limit = max(1, min(int(params.get('limit') or 20), 30))
        if mode == 'manual':
            rows = params.get('manual_samples') or []
        elif mode == 'uncategorized_recent':
            fallback_category_id = self.category_service.get_other_expense_category_id()
            if fallback_category_id is None:
                where = "category_id IS NULL"
                query_params = (limit,)
            else:
                where = """
                    (category_id IS NULL OR (
                        category_id = ? AND category_source = 'auto' AND category_rule_id IS NULL
                    ))
                """
                query_params = (fallback_category_id, limit)
            rows = self.dal.fetch_all(
                f"""
                SELECT id, channel, direction, amount_cents, counterparty, product_desc,
                       remark, payment_method, trade_type, category_id
                FROM unified_bills
                WHERE direction = 'expense'
                  AND is_deleted = 0
                  AND is_system = 0
                  AND is_category_manual_edited = 0
                  AND {where}
                ORDER BY trade_time DESC
                LIMIT ?
                """,
                query_params,
            )
        elif mode == 'selected_bills':
            bill_ids = [int(x) for x in (params.get('bill_ids') or [])[:30]]
            if not bill_ids:
                rows = []
            else:
                placeholders = ', '.join(['?' for _ in bill_ids])
                rows = self.dal.fetch_all(
                    f"""
                    SELECT id, channel, direction, amount_cents, counterparty, product_desc,
                           remark, payment_method, trade_type, category_id
                    FROM unified_bills
                    WHERE id IN ({placeholders}) AND is_deleted = 0 AND is_system = 0
                    LIMIT ?
                    """,
                    tuple(bill_ids) + (limit,),
                )
        else:
            raise ValueError('不支持的样本来源')
        return [self._sanitize_sample(dict(row)) for row in rows[:limit] if isinstance(row, dict) or hasattr(row, 'keys')]

    def _sanitize_sample(self, row: dict) -> dict:
        """
        清洗和标准化账单样本数据。

        提取关键字段并进行长度限制和类型转换。

        Args:
            row: 原始账单数据字典

        Returns:
            dict: 标准化后的样本字典，包含：
                - counterparty: 交易对手（最多 120 字符）
                - product_desc: 商品描述（最多 160 字符）
                - remark: 备注（最多 160 字符）
                - payment_method: 支付方式（最多 80 字符）
                - trade_type: 交易类型（最多 40 字符）
                - direction: 交易方向（最多 20 字符）
                - amount_yuan: 金额（元）
                - channel: 渠道（最多 40 字符）
        """
        return {
            'counterparty': str(row.get('counterparty') or '')[:120],
            'product_desc': str(row.get('product_desc') or '')[:160],
            'remark': str(row.get('remark') or '')[:160],
            'payment_method': str(row.get('payment_method') or '')[:80],
            'trade_type': str(row.get('trade_type') or '')[:40],
            'direction': str(row.get('direction') or '')[:20],
            'amount_yuan': round((int(row.get('amount_cents') or 0)) / 100, 2),
            'channel': str(row.get('channel') or '')[:40],
        }

    def _list_existing_keywords(self, category_id: int) -> list[dict]:
        """
        获取指定分类的现有关键词规则。

        Args:
            category_id: 分类 ID

        Returns:
            list[dict]: 现有关键词规则列表，每项包含：
                - keyword: 关键词
                - match_field: 匹配字段
                - weight: 权重
                - priority: 优先级
        """
        rows = self.dal.fetch_all(
            """
            SELECT keyword, match_field, weight, priority
            FROM category_keywords
            WHERE category_id = ? AND is_enabled = 1
            ORDER BY priority DESC, weight DESC, id ASC
            LIMIT 100
            """,
            (category_id,),
        )
        return [dict(row) for row in rows]

    def _build_conflict_lookup(self, category_id: int) -> dict[str, list[dict]]:
        """
        构建关键词冲突查找表。

        用于检测生成的关键词是否与其他分类的规则冲突。

        Args:
            category_id: 当前目标分类 ID

        Returns:
            dict[str, list[dict]]: 关键词到规则列表的映射，每项包含：
                - category_id: 分类 ID
                - category_name: 分类名称
                - match_field: 匹配字段
                - same_category: 是否与目标分类相同
        """
        rows = self.dal.fetch_all(
            """
            SELECT ck.keyword, ck.match_field, ck.category_id, bc.name AS category_name
            FROM category_keywords ck
            LEFT JOIN bill_categories bc ON bc.id = ck.category_id
            WHERE ck.is_enabled = 1
            """
        )
        lookup = {}
        for row in rows:
            item = dict(row)
            keyword = item.get('keyword') or ''
            lookup.setdefault(keyword, []).append({
                'category_id': item.get('category_id'),
                'category_name': item.get('category_name'),
                'match_field': item.get('match_field'),
                'same_category': item.get('category_id') == category_id,
            })
        return lookup

    def _normalize_apply_item(self, raw: dict, allowed_fields: set[str]) -> dict:
        """
        标准化应用项数据。

        验证并标准化用户选择要应用的建议项。

        Args:
            raw: 原始建议项字典
            allowed_fields: 允许的匹配字段集合

        Returns:
            dict: 标准化后的建议项，包含：
                - keyword: 关键词
                - match_field: 匹配字段
                - weight: 权重（1-100）
                - priority: 优先级（0-100）

        Raises:
            ValueError: 关键词为空或匹配字段无效时抛出
        """
        keyword = str(raw.get('keyword') or '').strip()
        if not keyword:
            raise ValueError('关键词不能为空')
        match_field = str(raw.get('match_field') or 'all_text').strip()
        if match_field not in allowed_fields:
            raise ValueError('匹配字段无效')
        return {
            'keyword': keyword,
            'match_field': match_field,
            'weight': max(1, min(100, int(raw.get('weight') or 10))),
            'priority': max(0, min(100, int(raw.get('priority') or 0))),
        }

    def _avg_confidence(self, items: list[dict]) -> float:
        """
        计算建议项的平均置信度。

        Args:
            items: 建议项列表

        Returns:
            float: 平均置信度（0-1），保留 4 位小数
        """
        if not items:
            return 0
        return round(sum(float(i.get('confidence') or 0) for i in items) / len(items), 4)

    def _response_diagnostic(self, raw: dict) -> str:
        """生成不包含完整模型内容的响应结构诊断。"""
        if not isinstance(raw, dict):
            return f'响应类型：{type(raw).__name__}'
        keys = ', '.join(str(key) for key in list(raw.keys())[:20]) or '无'
        suggestions = raw.get('suggestions')
        if 'suggestions' not in raw:
            suggestions_type = '缺失'
        elif isinstance(suggestions, list):
            suggestions_type = f'数组（{len(suggestions)}项）'
        else:
            suggestions_type = type(suggestions).__name__
        return f'响应顶层字段：{keys}；suggestions：{suggestions_type}'

    def _system_prompt(self) -> str:
        """
        获取 LLM 系统提示词。

        定义 AI 助手的角色和输出格式要求。

        Returns:
            str: 系统提示词字符串
        """
        return (
            '你是一个本地账单管理软件的分类规则助手。'
            '你的任务是根据账单样本，为指定消费分类生成关键词匹配规则建议。'
            '你需要分析账单样本中的交易对手、商品描述、备注等字段，提取有代表性的关键词。'
            '关键词必须从账单样本中提取，不要编造。'
            '你只能输出一个 JSON 对象，不要输出 Markdown、代码块或 JSON 之外的任何说明。'
            'JSON 顶层必须同时包含 summary 字符串和 suggestions 数组；禁止使用 items、data、result 等字段替代 suggestions。'
            'suggestions 数组中的每一项必须包含 keyword 字符串、match_field、weight 整数、priority 整数、reason 字符串、confidence 数字。'
            'match_field 只能使用输入数据 allowed_match_fields 中的 field_key；weight 范围为 1 到 100，priority 范围为 0 到 100，confidence 范围为 0 到 1。'
            '输出格式必须类似：{"summary":"识别出稳定关键词","suggestions":[{"keyword":"星巴克","match_field":"all_text","weight":30,"priority":10,"reason":"样本中多次出现","confidence":0.92}]}。'
            '规则必须保守，避免过泛关键词。不要生成会误伤大量账单的通用词。'
            '在交易对象可能有多种业务的情况下，尽量提取更全的、最能代表该分类的关键词，否则应该降低关键词的权重和优先级。'
        )