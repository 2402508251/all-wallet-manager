"""
信用消费与还款追踪 —— 识别花呗/白条/分付消费，追踪还款关联
"""
import uuid

from core.dal import DAL


class CreditTracker:
    CREDIT_KEYWORDS = ['花呗', '白条', '分付', '信用购', '分期']

    def __init__(self, dal: DAL):
        self.dal = dal

    def identify_credit(self, record: dict) -> dict | None:
        payment_method = record.get('payment_method', '')
        if not payment_method:
            return None

        is_credit = any(kw in payment_method for kw in self.CREDIT_KEYWORDS)
        if not is_credit:
            return None

        credit_account = self.dal.fetch_one(
            "SELECT * FROM credit_accounts WHERE account_name LIKE ?",
            (f'%{payment_method}%',),
        )

        return {
            'is_credit': True,
            'credit_account_id': credit_account['id'] if credit_account else None,
            'trade_type': 'credit_consumption',
        }

    def link_repayment(self, repayment_record: dict) -> dict | None:
        if repayment_record.get('trade_type') != 'repayment':
            return None

        source_account_id = repayment_record.get('account_id')
        if not source_account_id:
            return None

        credit_accounts = self.dal.fetch_all(
            "SELECT * FROM credit_accounts WHERE linked_account_id = ?",
            (source_account_id,),
        )
        if not credit_accounts:
            return None

        credit_account = credit_accounts[0]
        transfer_link_id = str(uuid.uuid4())

        return {
            'credit_account_id': credit_account['id'],
            'transfer_link_id': transfer_link_id,
            'is_credit': False,
        }

    def generate_mirror_record(self, repayment: dict) -> dict:
        """
        生成还款镜像记录：
        - channel_trade_no: 'MIRROR_' + 原始值
        - trade_type: repayment_mirror
        - direction: 与原始还款相反
        - is_system: 1
        - source_bill_id: NULL（系统生成，无源账单）
        - account_id: 信用账户关联的资金账户
        - role_id/family_id/assign_status: 从镜像账户派生
        """
        mirror = dict(repayment)
        mirror['direction'] = 'income' if repayment['direction'] == 'expense' else 'expense'
        mirror['trade_type'] = 'repayment_mirror'
        mirror['channel_trade_no'] = f"MIRROR_{repayment.get('channel_trade_no', '')}"
        mirror['is_system'] = 1
        mirror['is_manual_edited'] = 0
        mirror['source_bill_id'] = None

        credit_account_id = repayment.get('credit_account_id')
        if credit_account_id:
            credit_account = self.dal.fetch_one(
                "SELECT linked_account_id FROM credit_accounts WHERE id = ?",
                (credit_account_id,),
            )
            if credit_account and credit_account['linked_account_id']:
                mirror['account_id'] = credit_account['linked_account_id']
                account = self.dal.fetch_one(
                    "SELECT role_id FROM accounts WHERE id = ?",
                    (credit_account['linked_account_id'],),
                )
                if account and account['role_id']:
                    mirror['role_id'] = account['role_id']
                    primary_family = self.dal.fetch_one(
                        "SELECT family_id FROM role_families "
                        "WHERE role_id = ? AND is_primary = 1",
                        (account['role_id'],),
                    )
                    if primary_family:
                        mirror['family_id'] = primary_family['family_id']
                    mirror['assign_status'] = 'assigned'
                else:
                    mirror['role_id'] = None
                    mirror['family_id'] = None
                    mirror['assign_status'] = 'pending'

        for key in ('id', 'created_at', 'updated_at'):
            if key in mirror:
                del mirror[key]

        return mirror