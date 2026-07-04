"""
自动分配器 —— 账单导入后自动回填归属信息
"""
from core.dal import DAL


class AutoAssigner:
    def __init__(self, dal: DAL):
        self.dal = dal

    def assign(self, records: list[dict], account_id: int) -> list[dict]:
        account = self.dal.fetch_one(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        if not account:
            for r in records:
                r['assign_status'] = 'pending'
            return records

        role_id = account['role_id']
        family_id = None
        if role_id:
            primary_family = self.dal.fetch_one(
                "SELECT family_id FROM role_families "
                "WHERE role_id = ? AND is_primary = 1",
                (role_id,),
            )
            if primary_family:
                family_id = primary_family['family_id']

        default_family = self.dal.fetch_one(
            "SELECT * FROM families WHERE is_default = 1"
        )

        for record in records:
            record['account_id'] = account_id
            record['role_id'] = role_id

            if family_id:
                record['family_id'] = family_id
                record['assign_status'] = 'assigned'
            elif default_family:
                record['family_id'] = default_family['id']
                record['assign_status'] = 'assigned'
            else:
                record['family_id'] = None
                record['assign_status'] = 'pending'

        return records

    def assign_by_channel(self, records: list[dict], channel: str) -> list[dict]:
        accounts = self.dal.fetch_all(
            "SELECT * FROM accounts WHERE channel = ?", (channel,)
        )
        if not accounts:
            for r in records:
                r['assign_status'] = 'pending'
            return records

        if len(accounts) == 1:
            return self.assign(records, accounts[0]['id'])

        for record in records:
            record['assign_status'] = 'pending'

        return records