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


class SettingsMasterDataBridgeMixin:
    def get_families(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT f.*, "
            "(SELECT COUNT(DISTINCT rf.role_id) FROM role_families rf "
            " WHERE rf.family_id = f.id) as role_count "
            "FROM families f ORDER BY f.id"
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def create_family(self, params=None) -> dict:
        name = (params or {}).get('name', '')
        fid = self.dal.insert('families', {'name': name})
        return self.ok({'family_id': fid})

    def update_family(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        name = p.get('name')
        is_default = p.get('is_default')
        data = {}
        if name is not None:
            data['name'] = name
        try:
            with self.dal.transaction():
                if is_default is not None:
                    if is_default:
                        self.dal.execute("UPDATE families SET is_default = 0")
                    data['is_default'] = is_default
                self.dal.update('families', data, 'id = ?', (family_id,))
            return self.ok()
        except Exception as e:
            return self.err(f'更新家庭失败: {e}')

    def delete_family(self, params=None) -> dict:
        family_id = (params or {}).get('family_id')
        self.dal.delete('families', 'id = ?', (family_id,))
        return self.ok()

    def get_roles(self, params=None) -> dict:
        family_id = (params or {}).get('family_id')
        if family_id:
            rows = self.dal.fetch_all(
                "SELECT r.* FROM roles r "
                "JOIN role_families rf ON r.id = rf.role_id "
                "WHERE rf.family_id = ?", (family_id,))
        else:
            rows = self.dal.fetch_all("SELECT * FROM roles")
        return self.ok({'list': [dict(r) for r in rows]})

    def create_role(self, params=None) -> dict:
        p = params or {}
        name = p.get('name', '')
        family_id = p.get('family_id')
        role_type = p.get('role_type', 'personal')
        try:
            with self.dal.transaction():
                rid = self.dal.insert('roles', {
                    'name': name, 'role_type': role_type,
                })
                if family_id:
                    self.dal.insert('role_families', {
                        'role_id': rid, 'family_id': family_id,
                    })
            return self.ok({'role_id': rid})
        except Exception as e:
            return self.err(f'创建角色失败: {e}')

    def update_role(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        name = p.get('name')
        role_type = p.get('role_type')
        data = {}
        if name is not None:
            data['name'] = name
        if role_type is not None:
            data['role_type'] = role_type
        self.dal.update('roles', data, 'id = ?', (role_id,))
        return self.ok()

    def delete_role(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        self.dal.delete('roles', 'id = ?', (role_id,))
        return self.ok()

    def get_accounts(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        base_sql = (
            "SELECT a.*, r.name AS role_name, "
            "target.account_name AS canonical_account_name, "
            "target.id AS canonical_account_id, "
            "(SELECT COUNT(1) FROM account_aliases aa WHERE aa.account_id = a.id) AS alias_count "
            "FROM accounts a "
            "LEFT JOIN roles r ON a.role_id = r.id "
            "LEFT JOIN accounts target ON a.merged_into_account_id = target.id"
        )
        if role_id:
            rows = self.dal.fetch_all(
                f"{base_sql} WHERE a.role_id = ? ORDER BY a.id DESC", (role_id,)
            )
        else:
            rows = self.dal.fetch_all(f"{base_sql} ORDER BY a.id DESC")
        return self.ok({'list': [dict(r) for r in rows]})

    def _sync_account_bills_role(self, account_id: int, role_id, snapshot_type='account_role_change') -> int:
        bills = self.dal.fetch_all(
            "SELECT id FROM unified_bills WHERE account_id = ? AND is_deleted = 0",
            (account_id,),
        )
        bill_ids = [b['id'] for b in bills]
        if not bill_ids:
            return 0

        snapshot_id = self.snapshot.create_snapshot(
            snapshot_type,
            f'账户{account_id}角色变更，级联更新{len(bill_ids)}条账单',
            bill_ids,
        )

        new_assign_status = 'assigned' if role_id else 'pending'
        placeholders = ', '.join(['?' for _ in bill_ids])
        self.dal.execute(
            f"UPDATE unified_bills SET role_id = ?, assign_status = ?, updated_at = ? WHERE id IN ({placeholders})",
            (role_id, new_assign_status, self._now(), *bill_ids),
        )
        self.snapshot.finalize_snapshot(snapshot_id, bill_ids)
        return len(bill_ids)

    def get_account_aliases(self, params=None) -> dict:
        account_id = (params or {}).get('account_id')
        account = self.dal.fetch_one("SELECT id, channel FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.ok({'list': []})
        rows = self.dal.fetch_all(
            "SELECT * FROM account_aliases WHERE account_id = ? ORDER BY id DESC",
            (account_id,),
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def create_account_alias(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        alias_value = str(p.get('alias_value', '')).strip()
        alias_type = p.get('alias_type', 'wechat_nickname')
        account = self.dal.fetch_one("SELECT id, channel FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.err('当前仅支持维护微信账户曾用名')
        if not alias_value:
            return self.err('请输入曾用名')
        try:
            self.dal.insert_or_ignore('account_aliases', {
                'account_id': account_id,
                'channel': 'wechat',
                'alias_type': alias_type,
                'alias_value': alias_value,
                'source_kind': 'manual',
                'created_at': self._now(),
            })
            return self.ok()
        except Exception as e:
            return self.err(f'保存曾用名失败: {e}')

    def delete_account_alias(self, params=None) -> dict:
        alias_id = (params or {}).get('alias_id')
        deleted = self.dal.delete('account_aliases', 'id = ?', (alias_id,))
        return self.ok() if deleted else self.err('曾用名不存在')

    def merge_wechat_accounts(self, params=None) -> dict:
        p = params or {}
        source_id = p.get('source_account_id')
        target_id = p.get('target_account_id')
        if not source_id or not target_id or source_id == target_id:
            return self.err('请选择不同的源账户和目标账户')

        source = self.dal.fetch_one("SELECT * FROM accounts WHERE id = ?", (source_id,))
        target = self.dal.fetch_one("SELECT * FROM accounts WHERE id = ?", (target_id,))
        if not source or not target:
            return self.err('账户不存在')
        if source['channel'] != 'wechat' or target['channel'] != 'wechat':
            return self.err('当前仅支持合并微信账户')

        canonical_target_id = self._resolve_canonical_account_id(target_id)
        if canonical_target_id == source_id:
            return self.err('不能合并到自身或其下级账户')

        try:
            merge_session_id = str(uuid.uuid4())
            with self.dal.transaction():
                self.dal.update(
                    'accounts',
                    {'merged_into_account_id': canonical_target_id},
                    'id = ?',
                    (source_id,),
                )
                # 把源账户展示名中可识别的微信昵称沉淀为目标账户别名，减少后续导入裂变。
                self._add_wechat_alias(
                    canonical_target_id,
                    source['account_name'].replace('微信-', '').split('-')[0],
                    source_kind='merge_auto_added',
                    source_account_id=source_id,
                    merge_session_id=merge_session_id,
                )
            self._account_cache.clear()
            return self.ok({
                'source_account_id': source_id,
                'target_account_id': canonical_target_id,
                'merge_session_id': merge_session_id,
            })
        except Exception as e:
            return self.err(f'合并微信账户失败: {e}')

    def _retrace_related_real_payer_bills(self, account_ids: list[int]) -> dict:
        """局部重跑与指定账户相关的真实支付者溯源。"""
        account_ids = [aid for aid in account_ids if aid]
        if not account_ids:
            return {'groups_undone': 0, 'bills_retraced': 0, 'merged_count': 0}

        placeholders = ', '.join(['?' for _ in account_ids])
        affected_rows = self.dal.fetch_all(
            f"SELECT ub.id, ub.channel, ba.merged_group_id "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"WHERE ub.is_deleted = 0 AND (ub.account_id IN ({placeholders}) "
            f"OR ba.real_payer_account_id IN ({placeholders}))",
            tuple(account_ids) + tuple(account_ids),
        )
        group_ids = sorted({r['merged_group_id'] for r in affected_rows if r.get('merged_group_id')})
        bill_ids = {r['id'] for r in affected_rows}

        from modules.accounting.cross_platform_merger import CrossPlatformMerger
        merger = CrossPlatformMerger(self.dal)

        for group_id in group_ids:
            members = merger.get_merged_group(group_id)
            bill_ids.update(m['id'] for m in members)
            merger.undo_merge(group_id)

        orphan_rows = self.dal.fetch_all(
            f"SELECT ub.id FROM unified_bills ub "
            f"JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"WHERE ub.is_deleted = 0 AND ba.merge_status = 'orphan' "
            f"AND ub.account_id IN ({placeholders})",
            tuple(account_ids),
        )
        bill_ids.update(r['id'] for r in orphan_rows)

        bills = self.dal.fetch_all(
            f"SELECT * FROM unified_bills WHERE id IN ({', '.join(['?' for _ in bill_ids])}) AND is_deleted = 0 "
            f"ORDER BY trade_time ASC" if bill_ids else "SELECT * FROM unified_bills WHERE 1 = 0",
            tuple(bill_ids),
        )

        merged_count = 0
        retraced_count = 0
        for bill in bills:
            bill_dict = dict(bill)
            result = None
            if bill['channel'] in ('wechat', 'alipay'):
                result = merger.mark_orphan(bill_dict)
                retraced_count += 1
            elif bill['channel'] == 'ccb':
                result = merger.try_merge(bill_dict)
                retraced_count += 1
            if result and result.get('merged'):
                merged_count += 1

        return {
            'groups_undone': len(group_ids),
            'bills_retraced': retraced_count,
            'merged_count': merged_count,
        }

    def unmerge_wechat_account(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        remove_auto_added_target_aliases = bool(p.get('remove_auto_added_target_aliases', False))
        return_source_aliases = bool(p.get('return_source_aliases', False))
        retrace_related_bills = bool(p.get('retrace_related_bills', False))

        account = self.dal.fetch_one("SELECT id, channel, merged_into_account_id FROM accounts WHERE id = ?", (account_id,))
        if not account:
            return self.err('账户不存在')
        if account['channel'] != 'wechat':
            return self.err('当前仅支持微信账户取消合并')

        target_id = account.get('merged_into_account_id')
        result = {
            'detached': False,
            'removed_alias_count': 0,
            'returned_alias_count': 0,
            'retrace': None,
        }

        try:
            with self.dal.transaction():
                self.dal.update('accounts', {'merged_into_account_id': None}, 'id = ?', (account_id,))
                result['detached'] = True

                if remove_auto_added_target_aliases and target_id:
                    result['removed_alias_count'] = self.dal.delete(
                        'account_aliases',
                        "account_id = ? AND source_account_id = ? AND source_kind = ?",
                        (target_id, account_id, 'merge_auto_added'),
                    )

                if return_source_aliases and target_id:
                    result['returned_alias_count'] = self.dal.update(
                        'account_aliases',
                        {
                            'account_id': account_id,
                            'source_kind': 'manual',
                            'source_account_id': None,
                            'merge_session_id': None,
                        },
                        "account_id = ? AND source_account_id = ? AND source_kind = ?",
                        (target_id, account_id, 'merge_reassigned'),
                    )

            if retrace_related_bills:
                related_ids = [account_id]
                if target_id:
                    related_ids.append(target_id)
                result['retrace'] = self._retrace_related_real_payer_bills(related_ids)

            self._account_cache.clear()
            return self.ok(result)
        except Exception as e:
            return self.err(f'取消合并失败: {e}')

    def create_account(self, params=None) -> dict:
        p = params or {}
        account_name = p.get('account_name', '')
        account_tag = p.get('account_tag', '')
        channel = p.get('channel', '')
        role_id = p.get('role_id')
        aid = self.dal.insert('accounts', {
            'account_name': account_name,
            'account_tag': account_tag,
            'channel': channel,
            'role_id': role_id,
        })
        return self.ok({'account_id': aid})

    def update_account(self, params=None) -> dict:
        p = params or {}
        account_id = p.get('account_id')
        data = {k: v for k, v in p.items()
                if k in ('account_name', 'account_tag', 'channel', 'role_id')}

        try:
            with self.dal.transaction():
                if 'role_id' in data:
                    old_account = self.dal.fetch_one(
                        "SELECT role_id FROM accounts WHERE id = ?", (account_id,)
                    )
                    if old_account and old_account['role_id'] != data['role_id']:
                        self._sync_account_bills_role(account_id, data['role_id'])

                self.dal.update('accounts', data, 'id = ?', (account_id,))
            return self.ok()
        except Exception as e:
            return self.err(f'更新账户失败: {e}')

    def batch_assign_account_role(self, params=None) -> dict:
        p = params or {}
        account_ids = p.get('account_ids', [])
        role_id = p.get('role_id')
        if not account_ids:
            return self.err('未选择账户')
        if not role_id:
            return self.err('未选择目标角色')

        role = self.dal.fetch_one("SELECT id FROM roles WHERE id = ?", (role_id,))
        if not role:
            return self.err('目标角色不存在')

        placeholders = ', '.join(['?' for _ in account_ids])
        rows = self.dal.fetch_all(
            f"SELECT id, role_id FROM accounts WHERE id IN ({placeholders})",
            tuple(account_ids),
        )
        if len(rows) != len(account_ids):
            return self.err('部分账户不存在')

        updated_ids = []
        try:
            with self.dal.transaction():
                for row in rows:
                    account_id = row['id']
                    if row['role_id'] == role_id:
                        continue
                    self._sync_account_bills_role(account_id, role_id, 'batch_account_role_change')
                    self.dal.update('accounts', {'role_id': role_id}, 'id = ?', (account_id,))
                    updated_ids.append(account_id)
            return self.ok({'updated_count': len(updated_ids)})
        except Exception as e:
            return self.err(f'批量分配角色失败: {e}')

    def delete_account(self, params=None) -> dict:
        account_id = (params or {}).get('account_id')
        refs = [
            self.dal.fetch_one("SELECT id FROM unified_bills WHERE account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM bill_accounting WHERE real_payer_account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM credit_accounts WHERE linked_account_id = ? LIMIT 1", (account_id,)),
            self.dal.fetch_one("SELECT id FROM accounts WHERE merged_into_account_id = ? LIMIT 1", (account_id,)),
        ]
        if any(refs):
            return self.err('账户已被账单、真实支付者或合并关系引用，不能直接删除')
        with self.dal.transaction():
            self.dal.delete('account_aliases', 'account_id = ?', (account_id,))
            deleted = self.dal.delete('accounts', 'id = ?', (account_id,))
        return self.ok() if deleted else self.err('账户不存在')

    def get_categories(self, params=None) -> dict:
        rows = self.dal.fetch_all(
            "SELECT * FROM bill_categories ORDER BY level, parent_id, sort_order, id")
        return self.ok({'list': [dict(r) for r in rows]})

    def create_category(self, params=None) -> dict:
        p = params or {}
        name = p.get('name', '')
        icon = p.get('icon', '')
        parent_id = p.get('parent_id')
        level = 1
        if parent_id:
            parent = self.dal.fetch_one("SELECT id, level FROM bill_categories WHERE id = ?", (parent_id,))
            if not parent:
                return self.err('父分类不存在')
            if parent['level'] != 1:
                return self.err('仅支持两级分类')
            level = 2
        cid = self.dal.insert('bill_categories', {
            'name': name,
            'icon': icon,
            'parent_id': parent_id,
            'level': level,
            'sort_order': p.get('sort_order', 0),
            'source': 'user',
            'is_enabled': p.get('is_enabled', 1),
            'created_at': self._now(),
            'updated_at': self._now(),
        })
        return self.ok({'category_id': cid})

    def update_category(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        current = self.dal.fetch_one("SELECT * FROM bill_categories WHERE id = ?", (category_id,))
        if not current:
            return self.err('分类不存在')
        data = {}
        for key in ('name', 'icon', 'sort_order', 'is_enabled'):
            if p.get(key) is not None:
                data[key] = p.get(key)
        if 'parent_id' in p:
            parent_id = p.get('parent_id')
            if parent_id == category_id:
                return self.err('不能选择自身作为父分类')
            level = 1
            if parent_id:
                parent = self.dal.fetch_one("SELECT id, level FROM bill_categories WHERE id = ?", (parent_id,))
                if not parent:
                    return self.err('父分类不存在')
                if parent['level'] != 1:
                    return self.err('仅支持两级分类')
                child = self.dal.fetch_one("SELECT id FROM bill_categories WHERE parent_id = ? LIMIT 1", (category_id,))
                if child:
                    return self.err('已有子分类的一级分类不能改为二级分类')
                level = 2
            data['parent_id'] = parent_id
            data['level'] = level
        if not data:
            return self.ok()
        data['updated_at'] = self._now()
        self.dal.update('bill_categories', data, 'id = ?', (category_id,))
        return self.ok()

    def delete_category(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        category = self.dal.fetch_one("SELECT * FROM bill_categories WHERE id = ?", (category_id,))
        if not category:
            return self.err('分类不存在')
        if category.get('source') == 'system':
            return self.err('系统分类不能删除，可选择禁用')
        refs = [
            self.dal.fetch_one("SELECT id FROM bill_categories WHERE parent_id = ? LIMIT 1", (category_id,)),
            self.dal.fetch_one("SELECT id FROM category_keywords WHERE category_id = ? LIMIT 1", (category_id,)),
            self.dal.fetch_one("SELECT id FROM unified_bills WHERE category_id = ? LIMIT 1", (category_id,)),
        ]
        if any(refs):
            return self.err('分类已被子分类、规则或账单引用，不能删除')
        self.dal.delete('bill_categories', 'id = ?', (category_id,))
        return self.ok()

    def get_category_match_fields(self, params=None) -> dict:
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        return self.ok({'list': service.list_match_fields()})

    def get_category_keywords(self, params=None) -> dict:
        category_id = (params or {}).get('category_id')
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        rows = self.dal.fetch_all(
            "SELECT * FROM category_keywords WHERE category_id = ? ORDER BY priority DESC, weight DESC, id ASC",
            (category_id,))
        result = []
        for row in rows:
            item = dict(row)
            item['match_field'] = service.normalize_match_field(item.get('match_field') or 'counterparty')
            result.append(item)
        return self.ok({'list': result})

    def save_category_keywords(self, params=None) -> dict:
        p = params or {}
        category_id = p.get('category_id')
        keywords = p.get('keywords', [])
        from modules.categorizer import CategoryService
        service = CategoryService(self.dal)
        try:
            with self.dal.transaction():
                self.dal.delete('category_keywords', 'category_id = ?', (category_id,))
                for kw in keywords:
                    keyword = str(kw.get('keyword', '')).strip()
                    if not keyword:
                        continue
                    match_field = service.normalize_match_field(kw.get('match_field', 'counterparty'))
                    self.dal.insert('category_keywords', {
                        'category_id': category_id,
                        'keyword': keyword,
                        'match_field': match_field,
                        'weight': kw.get('weight', 10),
                        'priority': kw.get('priority', 0),
                        'match_mode': kw.get('match_mode', 'contains'),
                        'is_enabled': kw.get('is_enabled', 1),
                        'source': kw.get('source', 'user'),
                        'created_at': self._now(),
                        'updated_at': self._now(),
                    })
            return self.ok()
        except Exception as e:
            return self.err(f'保存关键词失败: {e}')

    def get_role_families(self, params=None) -> dict:
        role_id = (params or {}).get('role_id')
        rows = self.dal.fetch_all(
            "SELECT rf.*, f.name as family_name FROM role_families rf "
            "JOIN families f ON rf.family_id = f.id WHERE rf.role_id = ?",
            (role_id,),
        )
        return self.ok({'list': [dict(r) for r in rows]})

    def add_role_family(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        family_id = p.get('family_id')
        try:
            with self.dal.transaction():
                self.dal.insert_or_ignore('role_families', {
                    'role_id': role_id,
                    'family_id': family_id,
                })
            return self.ok()
        except Exception as e:
            return self.err(f'添加角色-家庭关联失败: {e}')

    def remove_role_family(self, params=None) -> dict:
        p = params or {}
        role_id = p.get('role_id')
        family_id = p.get('family_id')
        rf = self.dal.fetch_one(
            "SELECT 1 FROM role_families WHERE role_id = ? AND family_id = ?",
            (role_id, family_id),
        )
        if not rf:
            return self.err('关联不存在')

        self.dal.delete(
            'role_families',
            'role_id = ? AND family_id = ?',
            (role_id, family_id),
        )
        return self.ok()
