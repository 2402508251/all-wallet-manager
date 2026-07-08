"""
交易类型统一定义 —— 单一来源（Single Source of Truth）
所有交易类型相关常量和映射从此文件导出
"""

VALID_TRADE_TYPES = {
    'consumption',
    'credit_consumption',
    'refund',
    'transfer_out',
    'transfer_in',
    'repayment',
    'repayment_mirror',
    'fee',
    'topup',
    'withdrawal',
    'investment',
    'other_income',
    'other_expense',
    'other',
}

TRADE_TYPE_LABELS = {
    'consumption': '消费',
    'credit_consumption': '信用消费',
    'refund': '退款',
    'transfer_out': '转出',
    'transfer_in': '转入',
    'repayment': '还款',
    'repayment_mirror': '还款镜像',
    'fee': '手续费',
    'topup': '充值',
    'withdrawal': '提现',
    'investment': '理财',
    'other_income': '其他收入',
    'other_expense': '其他支出',
    'other': '其他',
}

INCOME_TYPES = {
    'topup', 'refund', 'transfer_in', 'other_income', 'repayment',
}

EXPENSE_TYPES = {
    'consumption', 'credit_consumption', 'fee', 'withdrawal',
    'transfer_out', 'other_expense', 'investment',
}

INTERNAL_FLOW_TYPES = {
    'transfer_out', 'transfer_in', 'repayment', 'repayment_mirror',
}

def get_trade_type_label(trade_type: str) -> str:
    return TRADE_TYPE_LABELS.get(trade_type, '未知')

def is_income_type(trade_type: str) -> bool:
    return trade_type in INCOME_TYPES

def is_expense_type(trade_type: str) -> bool:
    return trade_type in EXPENSE_TYPES

def is_internal_flow(trade_type: str) -> bool:
    return trade_type in INTERNAL_FLOW_TYPES

def validate_trade_type(trade_type: str) -> bool:
    return trade_type in VALID_TRADE_TYPES