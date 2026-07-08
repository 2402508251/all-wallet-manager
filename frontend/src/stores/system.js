// stores/system.js — 系统设置状态（家庭/角色/账户/分类/关键词/快照）

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'

export const useSystemStore = defineStore('system', {
  state: () => ({
    families: [],
    roles: [],
    accounts: [],
    categories: [],
    categoryKeywords: [],
    categoryMatchFields: [],
    snapshots: [],
    emails: [],
    currentFamilyId: null,
    currentRoleId: null,
    loading: false,
  }),

  actions: {
    // ─── 家庭 ────────────────────────────
    async loadFamilies() {
      const data = await call('get_families', {})
      this.families = data.list
    },

    async createFamily(name) {
      const data = await call('create_family', { name })
      await this.loadFamilies()
      return data.family_id
    },

    async updateFamily(familyId, fields) {
      await call('update_family', { family_id: familyId, ...fields })
      await this.loadFamilies()
    },

    async deleteFamily(familyId) {
      await call('delete_family', { family_id: familyId })
      await this.loadFamilies()
    },

    // ─── 角色 ────────────────────────────
    async loadRoles(familyId) {
      const data = await call('get_roles', { family_id: familyId })
      this.roles = data.list
    },

    async createRole(data) {
      const result = await call('create_role', data)
      await this.loadRoles(this.currentFamilyId)
      return result
    },

    async updateRole(roleId, fields) {
      await call('update_role', { role_id: roleId, ...fields })
      if (this.currentFamilyId) {
        await this.loadRoles(this.currentFamilyId)
      }
    },

    async deleteRole(roleId) {
      await call('delete_role', { role_id: roleId })
      if (this.currentFamilyId) {
        await this.loadRoles(this.currentFamilyId)
      }
    },

    async getRoleFamilies(roleId) {
      const data = await call('get_role_families', { role_id: roleId })
      return data.list
    },

    async addRoleFamily(roleId, familyId) {
      await call('add_role_family', { role_id: roleId, family_id: familyId })
    },

    async removeRoleFamily(roleId, familyId) {
      await call('remove_role_family', { role_id: roleId, family_id: familyId })
    },

    // ─── 账户 ────────────────────────────
    async loadAccounts(roleId) {
      const data = await call('get_accounts', { role_id: roleId })
      this.accounts = data.list
    },

    async createAccount(data) {
      await call('create_account', data)
      await this.loadAccounts(data.role_id)
    },

    async updateAccount(accountId, fields) {
      await call('update_account', { account_id: accountId, ...fields })
      await this.loadAccounts(this.currentRoleId)
    },

    async batchAssignAccountRole(accountIds, roleId) {
      const data = await call('batch_assign_account_role', { account_ids: accountIds, role_id: roleId })
      await this.loadAccounts(this.currentRoleId)
      return data
    },

    async deleteAccount(accountId) {
      await call('delete_account', { account_id: accountId })
      await this.loadAccounts(this.currentRoleId)
    },

    async loadAccountAliases(accountId) {
      const data = await call('get_account_aliases', { account_id: accountId })
      return data.list || []
    },

    async createAccountAlias(accountId, aliasValue, aliasType = 'wechat_nickname') {
      await call('create_account_alias', {
        account_id: accountId,
        alias_value: aliasValue,
        alias_type: aliasType,
      })
    },

    async deleteAccountAlias(aliasId) {
      await call('delete_account_alias', { alias_id: aliasId })
    },

    async mergeWechatAccounts(sourceAccountId, targetAccountId) {
      const data = await call('merge_wechat_accounts', {
        source_account_id: sourceAccountId,
        target_account_id: targetAccountId,
      })
      await this.loadAccounts(this.currentRoleId)
      return data
    },

    async unmergeWechatAccount(accountId, options = {}) {
      const data = await call('unmerge_wechat_account', { account_id: accountId, ...options })
      await this.loadAccounts(this.currentRoleId)
      return data
    },

    // ─── 分类 ────────────────────────────
    async loadCategories() {
      const data = await call('get_categories', {})
      this.categories = data.list
    },

    async createCategory(data) {
      await call('create_category', data)
      await this.loadCategories()
    },

    async updateCategory(categoryId, fields) {
      await call('update_category', { category_id: categoryId, ...fields })
      await this.loadCategories()
    },

    async deleteCategory(categoryId) {
      await call('delete_category', { category_id: categoryId })
      await this.loadCategories()
    },

    // ─── 分类关键词 ─────────────────────────
    async loadCategoryKeywords(categoryId) {
      const data = await call('get_category_keywords', { category_id: categoryId })
      this.categoryKeywords = data.list
    },

    async saveCategoryKeywords(categoryId, keywords) {
      await call('save_category_keywords', { category_id: categoryId, keywords })
      this.categoryKeywords = keywords
    },

    async loadCategoryMatchFields() {
      const data = await call('get_category_match_fields', {})
      this.categoryMatchFields = data.list
    },

    async recategorizeBills(scope, options = {}) {
      return await call('recategorize_bills', { scope, ...options })
    },

    async recategorizeBill(billId) {
      return await call('recategorize_bill', { bill_id: billId })
    },

    // ─── 邮箱 ────────────────────────────
    async loadEmails() {
      const data = await call('get_email_configs', {})
      this.emails = data.list
    },

    async saveEmail(config) {
      await call('save_email_config', config)
      await this.loadEmails()
    },

    async testEmailConnection(configId) {
      return await call('test_email_connection', { config_id: configId })
    },

    async deleteEmail(configId) {
      await call('delete_email_config', { config_id: configId })
      await this.loadEmails()
    },

    // ─── 快照 ────────────────────────────
    async loadSnapshots(limit = 20) {
      const data = await call('list_snapshots', { limit })
      this.snapshots = data.list
    },

    async getSnapshotDetails(snapshotId) {
      const data = await call('get_snapshot_details', { snapshot_id: snapshotId })
      return data.details
    },

    async restoreSnapshot(snapshotId) {
      await call('restore_snapshot', { snapshot_id: snapshotId })
      await this.loadSnapshots()
    },

    async deleteSnapshot(snapshotId) {
      await call('delete_snapshot', { snapshot_id: snapshotId })
      await this.loadSnapshots()
    },

    async createSnapshot(description) {
      const data = await call('create_snapshot', { description })
      await this.loadSnapshots()
      return data
    },

    // ─── 数据管理 ─────────────────────────
    async reparse(scope) {
      return await call('reparse', { scope })
    },

    async clearAllBills() {
      return await call('clear_all_bills', {})
    },

    async clearBillsByCollection(recordIds) {
      return await call('clear_bills_by_collection', { record_ids: recordIds })
    },

    async cleanupSourceBills(beforeDate) {
      return await call('cleanup_source_bills', { before_date: beforeDate })
    },

    async cleanupSnapshots(keepCount) {
      return await call('cleanup_snapshots', { keep_count: keepCount })
    },

    async resetApplication(options) {
      return await call('reset_application', options)
    },
  },
})
