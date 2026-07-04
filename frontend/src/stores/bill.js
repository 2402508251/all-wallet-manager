// stores/bill.js — 账单状态（筛选/列表/分页/详情/批量操作）

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'

export const useBillStore = defineStore('bill', {
  state: () => ({
    filter: {
      channel: null,
      family_id: null,
      role_id: null,
      account_id: null,
      category_id: null,
      direction: null,
      trade_type: null,
      assign_status: null,
      merge_status: null,
      start_time: null,
      end_time: null,
      keyword: '',
    },
    bills: [],
    total: 0,
    page: 1,
    pageSize: 20,
    currentBill: null,
    selectedIds: [],
    loading: false,
  }),

  actions: {
    async queryBills() {
      this.loading = true
      try {
        // 清理 null/空值
        const filters = {}
        for (const [k, v] of Object.entries(this.filter)) {
          if (v !== null && v !== '' && v !== undefined) {
            filters[k] = v
          }
        }

        const data = await call('query_bills', {
          filters,
          page: this.page,
          page_size: this.pageSize,
        })
        this.bills = data.list
        this.total = data.total
      } finally {
        this.loading = false
      }
    },

    async getBillDetail(billId) {
      const data = await call('get_bill_detail', { bill_id: billId })
      this.currentBill = data
      return data
    },

    async updateBill(billId, fields) {
      await call('update_bill', { bill_id: billId, fields })
      await this.queryBills()
    },

    async batchUpdateBills(billIds, fields) {
      await call('batch_update_bills', { bill_ids: billIds, fields })
      await this.queryBills()
      this.selectedIds = []
    },

    async deleteBill(billId) {
      await call('delete_bill', { bill_id: billId })
      await this.queryBills()
    },

    async deleteBills(billIds) {
      for (const id of billIds) {
        await call('delete_bill', { bill_id: id })
      }
      this.selectedIds = []
      await this.queryBills()
    },

    async restoreBill(billId) {
      await call('restore_bill', { bill_id: billId })
      await this.queryBills()
    },

    async permanentDeleteBill(billId) {
      await call('permanent_delete_bill', { bill_id: billId })
      await this.queryBills()
    },

    async getDeletedBills(page = 1, pageSize = 20) {
      const data = await call('get_deleted_bills', { page, page_size: pageSize })
      return data
    },

    async restoreDeletedBills(billIds) {
      await call('restore_deleted_bills', { bill_ids: billIds })
      await this.queryBills()
    },

    async permanentDeleteBills(billIds) {
      await call('permanent_delete_bills', { bill_ids: billIds })
      await this.queryBills()
    },

    async emptyRecycleBin() {
      await call('empty_recycle_bin', {})
      await this.queryBills()
    },

    async batchReassignBills(billIds, accountId) {
      await call('batch_reassign_bills', { bill_ids: billIds, account_id: accountId })
      await this.queryBills()
      this.selectedIds = []
    },

    async reassignBillFamily(billId, familyId) {
      await call('reassign_bill_family', { bill_id: billId, family_id: familyId })
      await this.queryBills()
    },

    async rollbackBatch(batchId) {
      await call('rollback_batch', { batch_id: batchId })
      await this.queryBills()
    },

    setFilter(filter) {
      Object.assign(this.filter, filter)
      this.page = 1
    },

    resetFilter() {
      this.filter = {
        channel: null,
        family_id: null,
        role_id: null,
        account_id: null,
        category_id: null,
        direction: null,
        trade_type: null,
        assign_status: null,
        merge_status: null,
        start_time: null,
        end_time: null,
        keyword: '',
      }
      this.page = 1
    },

    applyQueryFilter(query) {
      // 从路由 query 参数设置筛选条件
      if (query.category_id) this.filter.category_id = Number(query.category_id)
      if (query.direction) this.filter.direction = query.direction
      if (query.start_time) this.filter.start_time = query.start_time
      if (query.end_time) this.filter.end_time = query.end_time
      if (query.channel) this.filter.channel = query.channel
      if (query.family_id) this.filter.family_id = Number(query.family_id)
    },
  },
})