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

    async updateCreditAccount(id, fields) {
      await call('update_account', { account_id: id, ...fields })
      await this.loadCreditAccounts()
    },

    async loadCreditRecords(month, familyId) {
      const [year, m] = month.split('-').map(Number)
      const startTime = `${month}-01T00:00:00+08:00`
      const nextMonth = m === 12 ? 1 : m + 1
      const nextYear = m === 12 ? year + 1 : year
      const endTime = `${nextYear}-${String(nextMonth).padStart(2, '0')}-01T00:00:00+08:00`

      const filters = {
        trade_type: 'credit_consumption',
        start_time: startTime,
        end_time: endTime,
      }
      if (familyId) filters.family_id = familyId

      const data = await call('query_bills', {
        filters,
        page: 1,
        page_size: 100,
      })
      this.creditRecords = data.list
    },

    async loadRepayRecords(month, familyId) {
      const [year, m] = month.split('-').map(Number)
      const startTime = `${month}-01T00:00:00+08:00`
      const nextMonth = m === 12 ? 1 : m + 1
      const nextYear = m === 12 ? year + 1 : year
      const endTime = `${nextYear}-${String(nextMonth).padStart(2, '0')}-01T00:00:00+08:00`

      const filters = {
        trade_type: 'repayment',
        start_time: startTime,
        end_time: endTime,
      }
      if (familyId) filters.family_id = familyId

      const data = await call('query_bills', {
        filters,
        page: 1,
        page_size: 100,
      })
      this.repayRecords = data.list
    },

    // ─── 跨平台合并 ────────────────────────
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

    async undoMerge(mergedSourceId) {
      await call('undo_merge', { merged_source_id: mergedSourceId })
      await this.loadOrphanRecords()
    },

    // ─── 转账配对 ─────────────────────────
    async loadStrongPairs() {
      // 查询有 transfer_link_id 的记录
      const data = await call('query_bills', {
        filters: { trade_type: 'transfer_out' },
        page: 1,
        page_size: 200,
      })
      // 筛选有 transfer_link_id 的记录
      this.strongPairs = data.list.filter(b => b.transfer_link_id)
    },

    async loadWeakCandidates(page, pageSize) {
      const data = await call('query_bills', {
        filters: { trade_type: 'transfer_out' },
        page: page || 1,
        page_size: pageSize || 20,
      })
      // 筛选没有 transfer_link_id 的记录
      this.weakCandidates = data.list.filter(b => !b.transfer_link_id)
      this.weakTotal = this.weakCandidates.length
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

    async rejectTransferPair(candidateId) {
      await call('reject_transfer_pair', { candidate_id: candidateId })
      this.weakCandidates = this.weakCandidates.filter(c => c.id !== candidateId)
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