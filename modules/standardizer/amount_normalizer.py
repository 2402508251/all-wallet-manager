"""
金额标准化器 —— 金额字符串 → 整数分（Decimal 精确计算，避免浮点误差）
"""
import re
from decimal import Decimal, ROUND_HALF_UP


class AmountNormalizer:
    def normalize(self, raw_amount, direction_raw: str = None, channel: str = None) -> dict:
        """
        标准化金额，返回 { amount_cents: int, direction: str }

        规则：
        1. 去除所有非数字字符（¥、逗号、空格等），保留负号和小数点
        2. 使用 Decimal 精确计算：amount_cents = int(Decimal(value) * 100)
        3. 建行：金额含正负号，方向由正负判定
        4. 微信/支付宝：金额不含正负号，方向由收/支字段决定
        5. 金额为零时 direction = 'neutral'
        """
        if isinstance(raw_amount, (int, float)):
            raw_amount = str(raw_amount)

        # 清理：去除 ¥ 符号、千分位逗号、空格
        cleaned = re.sub(r'[¥￥,\s]', '', str(raw_amount))

        # 解析为 Decimal
        amount = Decimal(cleaned)

        if channel == 'ccb':
            # 建行：金额含正负号
            if amount < 0:
                direction = 'expense'
                amount_cents = int((-amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            elif amount > 0:
                direction = 'income'
                amount_cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            else:
                direction = 'neutral'
                amount_cents = 0
        else:
            # 微信/支付宝：金额为正数，方向由收/支决定
            amount_cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            direction = self._parse_direction(direction_raw)

        return {
            'amount_cents': amount_cents,
            'direction': direction,
        }

    def _parse_direction(self, direction_raw: str) -> str:
        """解析收/支方向"""
        if not direction_raw:
            return 'neutral'
        d = str(direction_raw).strip()
        if d in ('支出', 'expense', '支出（扣除）'):
            return 'expense'
        elif d in ('收入', 'income'):
            return 'income'
        elif d in ('不计入', '不计收支', 'neutral'):
            return 'neutral'
        return 'neutral'
