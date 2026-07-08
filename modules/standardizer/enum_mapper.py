"""
枚举值映射器 —— 将渠道原始枚举值映射为内部统一枚举值
"""
from core.config_manager import ConfigManager


class EnumMapper:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def map_trade_type(self, raw_type: str, channel: str,
                       payment_method: str = None) -> str:
        """
        映射交易类型：
        1. 从配置文件加载渠道枚举映射
        2. 精确匹配优先，匹配失败回退到 'other'
        3. 支付宝额外检查 payment_method 中的信用关键词
        """
        mappings = self.config.get_enum_mappings(channel)
        trade_type_map = mappings.get('trade_type', {})

        if raw_type in trade_type_map:
            mapped = trade_type_map[raw_type]
            return mapped

        return 'other'

    def finalize_trade_type(self, trade_type: str, direction: str) -> str:
        """按最终收支方向收敛交易类型，避免转入/转出与方向冲突"""
        if trade_type in ('transfer_in', 'transfer_out'):
            if direction == 'income':
                return 'transfer_in'
            if direction == 'expense':
                return 'transfer_out'
            return trade_type

        if trade_type != 'other':
            return trade_type
        if direction == 'income':
            return 'other_income'
        if direction == 'expense':
            return 'other_expense'
        return 'other'

    def map_direction(self, raw_direction: str, channel: str) -> str:
        """映射收支方向"""
        mappings = self.config.get_enum_mappings(channel)
        direction_map = mappings.get('direction', {})
        return direction_map.get(raw_direction, 'neutral')

    def is_credit_consumption(self, payment_method: str, channel: str) -> bool:
        if channel == 'alipay':
            mappings = self.config.get_enum_mappings(channel)
            credit_keywords = mappings.get('credit_keywords', [])
            if payment_method:
                method_str = str(payment_method).strip()
                for kw in credit_keywords:
                    if method_str == kw or method_str.startswith(kw + '(') or method_str.startswith(kw + '（'):
                        return True
        elif channel == 'wechat':
            credit_keywords = ['分付', '微信分付']
            if payment_method:
                method_str = str(payment_method).strip()
                for kw in credit_keywords:
                    if method_str == kw or method_str.startswith(kw + '(') or method_str.startswith(kw + '（'):
                        return True
        return False