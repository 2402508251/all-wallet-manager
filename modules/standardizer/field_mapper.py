"""
字段映射器 —— 将渠道原始字段名映射为统一账单模型字段名
"""


class FieldMapper:
    # 微信 → 统一字段
    WECHAT_MAPPING = {
        '交易时间': 'trade_time_raw',
        '交易类型': 'trade_type_raw',
        '交易对方': 'counterparty',
        '商品': 'product_desc',
        '收/支': 'direction_raw',
        '金额(元)': 'amount_raw',
        '支付方式': 'payment_method',
        '当前状态': 'status',
        '交易单号': 'channel_trade_no',
        '商户单号': 'merchant_trade_no',
        '备注': 'remark',
    }

    # 支付宝 → 统一字段
    ALIPAY_MAPPING = {
        '交易时间': 'trade_time_raw',
        '交易分类': 'trade_type_raw',
        '交易对方': 'counterparty',
        '对方账号': 'counterparty_account',
        '商品说明': 'product_desc',
        '收/支': 'direction_raw',
        '金额': 'amount_raw',
        '收/付款方式': 'payment_method',
        '交易状态': 'status',
        '交易订单号': 'channel_trade_no',
        '商家订单号': 'merchant_trade_no',
        '备注': 'remark',
    }

    # 建行 → 统一字段
    CCB_MAPPING = {
        '交易日期': 'trade_time_raw',
        '摘要': 'trade_type_raw',
        '交易金额': 'amount_raw',
        '账户余额': 'balance_raw',
        '交易地点/附言': 'product_desc',
        '对方账号与户名': 'counterparty_raw',
    }

    MAPPINGS = {
        'wechat': WECHAT_MAPPING,
        'alipay': ALIPAY_MAPPING,
        'ccb': CCB_MAPPING,
    }

    def map(self, raw_row: dict, channel: str) -> dict:
        """将渠道原始行数据映射为标准中间字段名"""
        mapping = self.MAPPINGS.get(channel, {})
        result = {}
        for src_key, dst_key in mapping.items():
            if src_key in raw_row:
                result[dst_key] = raw_row[src_key]
        return result
