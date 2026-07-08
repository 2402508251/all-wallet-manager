// stores/accounting.js — 账务处理状态（信用/合并/配对）

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'

export const useAccountingStore = defineStore('accounting', {
  state: () => ({
    activeTab: 'credit',
    creditAccounts: [],
    creditRecords: [],
    repayRecords: [],
    orphanRecords: [],
    orphanTotal: 0,
    orphanPage: 1,
    orphanPageSize: 20,
    mergedRecords: [],
    mergedTotal: 0,
    strongPairs: [],
    weakCandidates: [],
    weakTotal: 0,
    hideRepayment: false,
    loading: false,
  }),

  actions: {
    // ─── 信用消费 ─────────────────────────
    async loadCreditAccounts() {
      const data = await call('get_credit_accounts', {})
      this.creditAccounts = data.list
    },

    async createCreditAccount(fields) {
      await call('create_credit_account', fields)
      await this.loadCreditAccounts()
    },

    async updateCreditAccount(id, fields) {
      await call('update_credit_account', { credit_account_id: id, ...fields })
      await this.loadCreditAccounts()
    },

    async deleteCreditAccount(id) {
      await call('delete_credit_account', { credit_account_id: id })
      await this.loadCreditAccounts()
    },

    async loadCreditRecords(month, familyId, roleId) {
      const data = await call('get_credit_records', {
        month,
        family_id: familyId,
        role_id: roleId,
      })
      this.creditRecords = data.list
    },

    async loadRepayRecords(month, familyId, roleId) {
      const data = await call('get_repayment_records', {
        month,
        family_id: familyId,
        role_id: roleId,
      })
      this.repayRecords = data.list
    },

    // ─── 真实支付者溯源 ────────────────────────
    async loadOrphanRecords(page, pageSize) {
      if (page !== undefined) this.orphanPage = page
      if (pageSize !== undefined) this.orphanPageSize = pageSize

      const data = await call('get_orphan_records', {
        page: this.orphanPage,
        page_size: this.orphanPageSize,
      })
      this.orphanRecords = data.list
      this.orphanTotal = data.total
    },

    async confirmOrphanIndependent(billId) {
      await call('confirm_orphan_independent', { bill_id: billId })
      await this.loadOrphanRecords()
    },

    async tryMergeOrphan(billId) {
      const result = await call('try_merge_orphan', { bill_id: billId })
      await this.loadOrphanRecords()
      await this.loadMergedRecords()
      return result
    },

    async undoMerge(mergedGroupId) {
      await call('undo_merge', { merged_group_id: mergedGroupId })
      await this.loadOrphanRecords()
      await this.loadMergedRecords()
    },

    async loadMergedRecords(page, pageSize) {
      const data = await call('get_merged_records', {
        page: page || 1,
        page_size: pageSize || 50,
      })
      this.mergedRecords = data.list
      this.mergedTotal = data.total
    },

    // ─── 转账配对 ─────────────────────────
    async loadStrongPairs() {
      const data = await call('get_transfer_strong_pairs', {})
      this.strongPairs = data.list || []
    },

    async loadWeakCandidates() {
      const data = await call('get_transfer_weak_candidates', {})
      this.weakCandidates = data.list || []
      this.weakTotal = data.total || this.weakCandidates.length
    },

    async confirmTransferPair(outId, inId) {
      const data = await call('confirm_transfer_pair', {
        out_id: outId,
        in_id: inId,
      })
      await this.loadStrongPairs()
      await this.loadWeakCandidates()
      return data
    },

    async rejectTransferPair(outId, inId) {
      await call('reject_transfer_pair', { out_id: outId, in_id: inId })
      this.weakCandidates = this.weakCandidates.filter(c => !(c.out_bill_id === outId && c.in_bill_id === inId))
    },

    async getWeakMatchCandidates(billId) {
      const data = await call('get_weak_match_candidates', { bill_id: billId })
      return data.candidates || []
    },

    // ─── 隐藏还款 ─────────────────────────
    async toggleHideRepayment(hide) {
      await call('toggle_hide_repayment_transfer', { hide })
      this.hideRepayment = hide
    },
  },
})
