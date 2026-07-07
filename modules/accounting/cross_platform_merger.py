"""
跨平台支付合并 —— 将支付宝/微信第三方支付与银行卡扣款记录合并
核心设计原则：
- 合并不删除账单：匹配成功后保留所有账单记录，仅建立合并关联关系
- 账户层面：真实支付者消费（实际扣款的账户）
- 角色层面：付款者消费（发起交易的账户所属角色）

合并场景：
1. 支付宝/微信使用银行卡支付（第三方支付记录 + 银行卡流水）
2. 微信亲属卡支付（代付者账户记录 + 被代付者账户记录）
"""
import logging
import re
import uuid
from datetime import datetime

from core.dal import DAL


logger = logging.getLogger(__name__)


class CrossPlatformMerger:
    # 第三方平台关键词（用于识别银行卡流水中的第三方支付）
    THIRD_PARTY_KEYWORDS = ['微信', '支付宝', '财付通', 'Alipay', 'WeChat']
    # 亲属卡关键词（用于识别亲属卡支付）
    FAMILY_CARD_KEYWORDS = ['亲属卡', '亲属支付', '代付']
    # 分场景时间阈值：第三方即时支付在“双方都有具体时间”时更严格；
    # 但建行只有日期时需要放宽到按日粒度匹配。
    INSTANT_THRESHOLD_HOURS = 0.5
    DATE_ONLY_THRESHOLD_HOURS = 24
    FAMILY_CARD_THRESHOLD_HOURS = 24
    DEFAULT_THRESHOLD_HOURS = 24

    def __init__(self, dal: DAL):
        self.dal = dal

    def get_time_threshold(self, search_text: str = '',
                           source_trade_time: str = '', target_trade_time: str = '') -> float:
        """根据匹配场景和时间粒度返回小时级阈值。"""
        search_text = search_text or ''

        # 建行账单通常只有日期，被标准化后时间固定为 00:00:00，需要放宽到按日粒度
        if str(source_trade_time).endswith('T00:00:00+08:00') or str(target_trade_time).endswith('T00:00:00+08:00'):
            return self.DATE_ONLY_THRESHOLD_HOURS

        if any(kw in search_text for kw in self.FAMILY_CARD_KEYWORDS):
            return self.FAMILY_CARD_THRESHOLD_HOURS
        if any(kw in search_text for kw in self.THIRD_PARTY_KEYWORDS):
            return self.INSTANT_THRESHOLD_HOURS
        return self.DEFAULT_THRESHOLD_HOURS

    def is_orphan_payment_method(self, channel: str, payment_method: str) -> bool:
        """判断某支付方式是否属于可进入 orphan 的第三方支付账户。"""
        payment_method = str(payment_method or '')
        if channel == 'wechat':
            keywords = ('银行', '储蓄卡', '信用卡', '亲属卡')
        elif channel == 'alipay':
            keywords = ('银行', '储蓄卡', '信用卡')
        else:
            return False
        return any(kw in payment_method for kw in keywords)

    def extract_card_suffix(self, text: str) -> str:
        """从支付方式、账户标识或账户名中提取 4 位银行卡尾号。"""
        text = str(text or '')
        match = re.search(r'\((\d{4})\)', text)
        if match:
            return match.group(1)
        match = re.search(r'(?:_|-|（)(\d{4})(?:\)|）)?$', text)
        if match:
            return match.group(1)
        digits = re.findall(r'\d{4}', text)
        return digits[-1] if digits else ''

    def extract_family_card_name(self, text: str) -> str:
        """从亲属卡相关文本中尽量提取代付者/持卡人昵称。"""
        text = str(text or '').strip()
        if '亲属卡' not in text:
            return ''
        patterns = (
            r'([^\s（）()，,：:]+)的亲属卡',
            r'亲属卡[（(]([^）)]+)[）)]',
            r'亲属卡[：:]\s*([^\s，,]+)',
            r'亲属卡-([^\s，,]+)',
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                if name and name not in ('亲属卡', '支付'):
                    return name
        return ''

    def resolve_alias_account_id(self, alias_value: str) -> int | None:
        alias_value = str(alias_value or '').strip()
        if not alias_value:
            return None
        row = self.dal.fetch_one(
            "SELECT aa.account_id, a.merged_into_account_id "
            "FROM account_aliases aa "
            "JOIN accounts a ON aa.account_id = a.id "
            "WHERE aa.channel = 'wechat' AND aa.alias_value = ? "
            "ORDER BY aa.id DESC LIMIT 1",
            (alias_value,),
        )
        if not row:
            return None
        return row.get('merged_into_account_id') or row.get('account_id')

    def resolve_canonical_account_id(self, account_id: int) -> int | None:
        if not account_id:
            return None
        seen = set()
        current_id = account_id
        while current_id and current_id not in seen:
            seen.add(current_id)
            row = self.dal.fetch_one(
                "SELECT merged_into_account_id FROM accounts WHERE id = ?",
                (current_id,),
            )
            if not row or not row.get('merged_into_account_id'):
                return current_id
            current_id = row['merged_into_account_id']
        return account_id

    def get_account_card_suffix(self, account_id: int) -> str:
        if not account_id:
            return ''
        row = self.dal.fetch_one(
            "SELECT account_tag, account_name FROM accounts WHERE id = ?",
            (account_id,),
        )
        if not row:
            return ''
        return self.extract_card_suffix(f"{row.get('account_tag', '')} {row.get('account_name', '')}")

    def scan_orphans(self) -> list[dict]:
        """
        扫描孤儿记录（发起方记录未找到真实支付者）：
        查询 bill_accounting.merge_status = 'orphan' 的记录
        """
        rows = self.dal.fetch_all(
            "SELECT ub.*, ba.merge_status, ba.transfer_link_id, ba.merged_group_id "
            "FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ba.merge_status = 'orphan' AND ub.is_deleted = 0 "
            "ORDER BY ub.trade_time DESC"
        )
        return [dict(r) for r in rows]

    def try_merge(self, real_payer_record: dict) -> dict | None:
        """
        真实支付者记录（银行卡/代付方）导入时，尝试与已有发起方孤儿记录合并：

        匹配条件：
        - 真实支付者记录的 product_desc / remark 包含第三方平台/亲属卡关键词
        - 金额一致（amount_cents 相等）
        - 时间差 ≤ 合理范围（跨渠道 ≤ 48小时）

        匹配成功：
        - 生成 merged_group_id（UUID）
        - 真实支付者记录（merged_target）：
          * bill_accounting.merge_status = 'merged_target'
          * bill_accounting.merged_group_id = 生成的UUID
          * bill_accounting.real_payer_account_id = 自身账户ID
          * 保存 original_counterparty 和 original_product_desc
          * 用发起方记录的信息**完善**（补充而非覆盖）
        - 发起方记录（merged_source）：
          * bill_accounting.merge_status = 'merged_source'
          * bill_accounting.merged_group_id = 同一UUID
          * bill_accounting.real_payer_account_id = 真实支付者账户ID
          * unified_bills.is_deleted = 0（不删除，保留记录）
          * 保持原有的 role_id（角色层面：付款者消费）
        """
        amount = real_payer_record.get('amount_cents', 0)
        trade_time = real_payer_record.get('trade_time', '')
        product_desc = real_payer_record.get('product_desc', '')
        remark = real_payer_record.get('remark', '')
        channel = real_payer_record.get('channel', '')
        real_payer_account_id = real_payer_record.get('account_id')

        # 检查是否为跨平台支付场景
        if channel != 'ccb':
            logger.info("try_merge skipped: bill_id=%s channel=%s reason=not_ccb", real_payer_record.get('id'), channel)
            return None

        search_text = f"{product_desc} {remark}"
        is_third_party = any(kw in search_text for kw in self.THIRD_PARTY_KEYWORDS)
        is_family_card = any(kw in search_text for kw in self.FAMILY_CARD_KEYWORDS)

        if not (is_third_party or is_family_card):
            logger.info("try_merge skipped: bill_id=%s reason=no_keyword", real_payer_record.get('id'))
            return None

        threshold_hours = self.get_time_threshold(
            search_text,
            source_trade_time=trade_time,
            target_trade_time='',
        )

        with self.dal.transaction():
            # 查找金额匹配的孤儿记录
            orphans = self.dal.fetch_all(
                "SELECT ub.*, ba.id as accounting_id "
                "FROM unified_bills ub "
                "JOIN bill_accounting ba ON ub.id = ba.bill_id "
                "WHERE ba.merge_status = 'orphan' AND ub.is_deleted = 0 "
                "AND ub.amount_cents = ? AND ub.direction = ?",
                (amount, real_payer_record.get('direction', 'expense')),
            )

            # 找最佳匹配：优先账户身份线索，其次时间差
            best_match = None
            best_score = -1
            best_time_diff = float('inf')
            real_payer_card_suffix = self.get_account_card_suffix(real_payer_account_id)
            canonical_real_payer_account_id = self.resolve_canonical_account_id(real_payer_account_id)

            for orphan in orphans:
                try:
                    t1 = datetime.fromisoformat(trade_time)
                    t2 = datetime.fromisoformat(orphan['trade_time'])
                    diff_hours = abs((t1 - t2).total_seconds()) / 3600
                    if diff_hours > threshold_hours:
                        continue

                    score = 0
                    orphan_payment_method = orphan.get('payment_method', '')
                    orphan_card_suffix = self.extract_card_suffix(orphan_payment_method)
                    if orphan_card_suffix and real_payer_card_suffix:
                        if orphan_card_suffix != real_payer_card_suffix:
                            continue
                        score += 100

                    family_name = self.extract_family_card_name(orphan_payment_method)
                    alias_account_id = self.resolve_alias_account_id(family_name)
                    if alias_account_id and alias_account_id == canonical_real_payer_account_id:
                        score += 150

                    if score > best_score or (score == best_score and diff_hours < best_time_diff):
                        best_score = score
                        best_time_diff = diff_hours
                        best_match = orphan
                except (ValueError, TypeError):
                    continue

            if not best_match:
                logger.info(
                    "try_merge no_match: bill_id=%s candidates=%s threshold_hours=%s",
                    real_payer_record.get('id'), len(orphans), threshold_hours,
                )
                return None

            # 生成合并组ID
            merged_group_id = str(uuid.uuid4())

            # 完善真实支付者记录的商品说明
            bank_counterparty = real_payer_record.get('counterparty', '')
            bank_product_desc = product_desc
            initiator_counterparty = best_match['counterparty'] or ''
            initiator_product_desc = best_match['product_desc'] or ''

            DEFAULT_COUNTERPARTIES = {'银联', '', '—', '-'}

            if not bank_counterparty or bank_counterparty in DEFAULT_COUNTERPARTIES:
                new_counterparty = initiator_counterparty
            else:
                new_counterparty = f"{bank_counterparty} | {initiator_counterparty}" if initiator_counterparty else bank_counterparty

            channel_label = '微信' if '微信' in search_text or 'WeChat' in search_text else '支付宝'
            new_product_desc = f"{bank_product_desc} | [{channel_label}] {initiator_product_desc}" if initiator_product_desc else bank_product_desc

            # 更新真实支付者记录
            self.dal.update(
                'unified_bills',
                {
                    'counterparty': new_counterparty,
                    'product_desc': new_product_desc,
                },
                'id = ?',
                (real_payer_record.get('id'),),
            )

            # 创建或更新真实支付者的账务记录（merged_target）
            existing_accounting = self.dal.fetch_one(
                "SELECT id FROM bill_accounting WHERE bill_id = ?",
                (real_payer_record.get('id'),),
            )
            if existing_accounting:
                self.dal.update(
                    'bill_accounting',
                    {
                        'merge_status': 'merged_target',
                        'merged_group_id': merged_group_id,
                        'real_payer_account_id': real_payer_account_id,
                        'original_counterparty': bank_counterparty,
                        'original_product_desc': bank_product_desc,
                    },
                    'bill_id = ?',
                    (real_payer_record.get('id'),),
                )
            else:
                self.dal.insert('bill_accounting', {
                    'bill_id': real_payer_record.get('id'),
                    'merge_status': 'merged_target',
                    'merged_group_id': merged_group_id,
                    'real_payer_account_id': real_payer_account_id,
                    'original_counterparty': bank_counterparty,
                    'original_product_desc': bank_product_desc,
                })

            # 更新发起方记录的账务状态（不删除账单，保留 role_id/family_id）
            # 清除 orphan 状态，设为 merged_source
            self.dal.update(
                'bill_accounting',
                {
                    'merge_status': 'merged_source',
                    'merged_group_id': merged_group_id,
                    'real_payer_account_id': real_payer_account_id,  # 指向真实支付者
                },
                'bill_id = ?',
                (best_match['id'],),
            )

            logger.info(
                "try_merge success: group=%s real_payer_bill_id=%s initiator_bill_id=%s diff_hours=%.4f",
                merged_group_id, real_payer_record.get('id'), best_match['id'], best_time_diff,
            )

        return {
            'merged': True,
            'merged_group_id': merged_group_id,
            'real_payer_bill_id': real_payer_record.get('id'),
            'initiator_bill_id': best_match['id'],
        }

    def mark_orphan(self, initiator_record: dict) -> dict:
        """
        发起方记录（第三方支付/亲属卡被代付方）导入时，尝试匹配真实支付者记录：

        1. 查找金额一致 + 时间接近的真实支付者记录
        2. 匹配成功 → 合并（完善逻辑同 try_merge）
        3. 无匹配 → 在 bill_accounting 创建 merge_status='orphan'，等待后续匹配
        """
        bill_id = initiator_record.get('id')
        if not bill_id:
            return {'marked': True, 'orphan': True}

        channel = initiator_record.get('channel', '')
        if channel not in ('wechat', 'alipay'):
            logger.info("mark_orphan skipped: bill_id=%s channel=%s reason=not_initiator_channel", bill_id, channel)
            return {'marked': False, 'orphan': False}

        payment_method = str(initiator_record.get('payment_method', '') or '')
        if not self.is_orphan_payment_method(channel, payment_method):
            logger.info(
                "mark_orphan skipped: bill_id=%s payment_method=%s reason=not_third_party_account",
                bill_id, payment_method,
            )
            return {'marked': False, 'orphan': False}

        # 先尝试查找已存在的真实支付者记录
        amount = initiator_record.get('amount_cents', 0)
        trade_time = initiator_record.get('trade_time', '')
        direction = initiator_record.get('direction', 'expense')

        # 查找银行卡记录（可能已导入）
        potential_targets = self.dal.fetch_all(
            "SELECT ub.*, ba.id as accounting_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.channel = 'ccb' AND ub.is_deleted = 0 "
            "AND ub.amount_cents = ? AND ub.direction = ? "
            "AND (ba.merge_status IS NULL OR ba.merge_status = 'normal')",
            (amount, direction),
        )

        # 检查是否包含第三方关键词，并用账户身份线索增强排序
        best_match = None
        best_score = -1
        best_time_diff = float('inf')
        initiator_card_suffix = self.extract_card_suffix(payment_method)
        family_name = self.extract_family_card_name(payment_method)
        alias_account_id = self.resolve_alias_account_id(family_name)

        for target in potential_targets:
            search_text = f"{target.get('product_desc', '')} {target.get('remark', '')}"
            is_third_party = any(kw in search_text for kw in self.THIRD_PARTY_KEYWORDS)
            is_family_card = any(kw in search_text for kw in self.FAMILY_CARD_KEYWORDS)

            if not (is_third_party or is_family_card):
                continue

            try:
                t1 = datetime.fromisoformat(trade_time)
                t2 = datetime.fromisoformat(target['trade_time'])
                diff_hours = abs((t1 - t2).total_seconds()) / 3600
                threshold_hours = self.get_time_threshold(
                    search_text,
                    source_trade_time=trade_time,
                    target_trade_time=target['trade_time'],
                )
                if diff_hours > threshold_hours:
                    continue

                score = 0
                target_card_suffix = self.get_account_card_suffix(target.get('account_id'))
                if initiator_card_suffix and target_card_suffix:
                    if initiator_card_suffix != target_card_suffix:
                        continue
                    score += 100

                if alias_account_id and alias_account_id == self.resolve_canonical_account_id(target.get('account_id')):
                    score += 150

                if score > best_score or (score == best_score and diff_hours < best_time_diff):
                    best_score = score
                    best_time_diff = diff_hours
                    best_match = target
            except (ValueError, TypeError):
                continue

        # 先把当前发起方记录写成 orphan；若已有匹配目标，try_merge 才能查到它
        with self.dal.transaction():
            existing = self.dal.fetch_one(
                "SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,)
            )
            if existing:
                self.dal.update(
                    'bill_accounting',
                    {
                        'merge_status': 'orphan',
                        'merged_group_id': None,
                        'real_payer_account_id': None,
                    },
                    'bill_id = ?',
                    (bill_id,),
                )
            else:
                self.dal.insert('bill_accounting', {
                    'bill_id': bill_id,
                    'merge_status': 'orphan',
                })

        if best_match:
            logger.info(
                "mark_orphan matched_existing_target: bill_id=%s target_bill_id=%s diff_hours=%.4f",
                bill_id, best_match['id'], best_time_diff,
            )
            # 找到了真实支付者，执行合并（try_merge 内部已使用事务）
            result = self.try_merge(best_match)
            if result:
                return result

        logger.info(
            "mark_orphan success: bill_id=%s candidates=%s",
            bill_id, len(potential_targets),
        )
        return {'marked': True, 'orphan': True}

    def undo_merge(self, merged_group_id: str) -> dict:
        """
        撤销合并：

        1. 查询 merged_group_id 关联的所有记录
        2. 恢复发起方记录：
           - bill_accounting.merge_status = 'orphan'
           - 清空 merged_group_id 和 real_payer_account_id
        3. 恢复真实支付者记录：
           - bill_accounting.merge_status = 'normal'
           - 清空 merged_group_id / real_payer_account_id / original_* 备份字段
           - 恢复原始 product_desc / counterparty
        4. 返回恢复结果
        """
        with self.dal.transaction():
            # 查询合并组内的所有记录
            merged_records = self.dal.fetch_all(
                "SELECT ba.bill_id, ba.merge_status, ba.original_counterparty, ba.original_product_desc, "
                "ba.real_payer_account_id "
                "FROM bill_accounting ba "
                "WHERE ba.merged_group_id = ?",
                (merged_group_id,),
            )

            if not merged_records:
                logger.warning("undo_merge no_group: group=%s", merged_group_id)
                return {'success': False, 'message': '未找到合并组记录'}

            initiator_id = None
            real_payer_id = None

            for record in merged_records:
                if record['merge_status'] == 'merged_source':
                    initiator_id = record['bill_id']
                elif record['merge_status'] == 'merged_target':
                    real_payer_id = record['bill_id']

            # 恢复发起方记录为孤儿状态
            if initiator_id:
                self.dal.update(
                    'bill_accounting',
                    {
                        'merge_status': 'orphan',
                        'merged_group_id': None,
                        'real_payer_account_id': None,
                    },
                    'bill_id = ?',
                    (initiator_id,),
                )

            # 恢复真实支付者记录
            if real_payer_id:
                # 恢复原始商品说明
                real_payer_accounting = self.dal.fetch_one(
                    "SELECT original_counterparty, original_product_desc "
                    "FROM bill_accounting WHERE bill_id = ?",
                    (real_payer_id,),
                )
                if real_payer_accounting:
                    restore_data = {}
                    if real_payer_accounting['original_counterparty'] is not None:
                        restore_data['counterparty'] = real_payer_accounting['original_counterparty']
                    if real_payer_accounting['original_product_desc'] is not None:
                        restore_data['product_desc'] = real_payer_accounting['original_product_desc']
                    if restore_data:
                        self.dal.update(
                            'unified_bills',
                            restore_data,
                            'id = ?',
                            (real_payer_id,),
                        )

                # 重置真实支付者的账务记录，保留 bill_accounting 行
                self.dal.update(
                    'bill_accounting',
                    {
                        'merge_status': 'normal',
                        'merged_group_id': None,
                        'real_payer_account_id': None,
                        'original_counterparty': None,
                        'original_product_desc': None,
                    },
                    'bill_id = ?',
                    (real_payer_id,),
                )

            logger.info(
                "undo_merge success: group=%s initiator_id=%s real_payer_id=%s",
                merged_group_id, initiator_id, real_payer_id,
            )

        return {
            'success': True,
            'restored_initiator_id': initiator_id,
            'restored_real_payer_id': real_payer_id,
        }

    def get_merged_group(self, merged_group_id: str) -> list[dict]:
        """
        获取合并组内的所有记录：
        返回真实支付者记录和发起方记录，用于展示合并详情
        """
        rows = self.dal.fetch_all(
            "SELECT ub.*, ba.merge_status, ba.merged_group_id, ba.real_payer_account_id "
            "FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ba.merged_group_id = ?",
            (merged_group_id,),
        )
        return [dict(r) for r in rows]

    def get_real_payer_consumption(self, account_id: int, date_range: tuple = None) -> dict:
        """
        获取账户层面的消费统计（真实支付者）：
        - 合并记录：bill_accounting.real_payer_account_id = account_id
        - 未合并记录（normal/orphan）：unified_bills.account_id = account_id
          （发起方账单未合并时，账户归属仍为发起方账户）
        """
        query = (
            "SELECT ub.id, ub.trade_time, ub.amount_cents, ub.counterparty, ub.product_desc, "
            "ba.merge_status, ba.merged_group_id, ba.real_payer_account_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.is_deleted = 0 AND ub.direction = 'expense' "
            "AND (ba.real_payer_account_id = ? "
            "OR ((ba.merge_status IS NULL OR ba.merge_status IN ('normal', 'orphan')) AND ub.account_id = ?))"
        )
        params = [account_id, account_id]

        if date_range:
            query += " AND ub.trade_time BETWEEN ? AND ?"
            params.extend(date_range)

        rows = self.dal.fetch_all(query, params)
        return {
            'account_id': account_id,
            'bills': [dict(r) for r in rows],
            'total_amount': sum(r['amount_cents'] for r in rows),
        }

    def get_role_consumption(self, role_id: int, date_range: tuple = None) -> dict:
        """
        获取角色层面的消费统计（付款者）：
        - 合并记录：发起方记录的 role_id（付款者所属角色）
        - 未合并记录（normal/orphan）：unified_bills.role_id
          （发起方账单未合并时，角色归属不变）
        """
        # 查询合并记录中发起方的 role_id
        query = (
            "SELECT ub.id, ub.trade_time, ub.amount_cents, ub.counterparty, ub.product_desc, "
            "ba.merge_status, ba.merged_group_id, ub.role_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.is_deleted = 0 AND ub.direction = 'expense' "
            "AND ub.role_id = ?"
        )
        params = [role_id]

        if date_range:
            query += " AND ub.trade_time BETWEEN ? AND ?"
            params.extend(date_range)

        rows = self.dal.fetch_all(query, params)
        return {
            'role_id': role_id,
            'bills': [dict(r) for r in rows],
            'total_amount': sum(r['amount_cents'] for r in rows),
        }