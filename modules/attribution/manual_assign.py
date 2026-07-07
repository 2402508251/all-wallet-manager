"""
手动分配器 —— 用户手动给账单指定角色（家庭通过角色自动关联）
"""
from core.dal import DAL


class ManualAssigner:
    def __init__(self, dal: DAL):
        self.dal = dal

    def batch_assign(self, bill_ids: list[int], role_id: int) -> int:
        """批量分配角色，仅更新 role_id 与分配状态"""
        if not bill_ids:
            return 0

        data = {
            'role_id': role_id,
            'assign_status': 'assigned' if role_id else 'pending',
        }

        placeholders = ', '.join(['?' for _ in bill_ids])
        updated = self.dal.update(
            'unified_bills',
            data,
            f'id IN ({placeholders})',
            tuple(bill_ids),
        )
        return updated

    def get_roles_by_family(self, family_id: int) -> list[dict]:
        """获取家庭下的角色列表（通过 role_families 多对多查询）"""
        rows = self.dal.fetch_all(
            "SELECT r.* FROM roles r "
            "JOIN role_families rf ON rf.role_id = r.id "
            "WHERE rf.family_id = ?",
            (family_id,),
        )
        return [dict(r) for r in rows]

    def get_families_by_role(self, role_id: int) -> list[dict]:
        """获取角色关联的家庭（通过 role_families 多对多查询）"""
        rows = self.dal.fetch_all(
            "SELECT f.* FROM families f "
            "JOIN role_families rf ON rf.family_id = f.id "
            "WHERE rf.role_id = ?",
            (role_id,),
        )
        return [dict(r) for r in rows]