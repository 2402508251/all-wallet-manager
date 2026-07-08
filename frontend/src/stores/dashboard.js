// stores/dashboard.js - dashboard aggregate state from existing APIs

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'
import { currentMonthParts, monthDateRange } from '@/utils/formatters'

function formatMonth(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`
}

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    filter: {
      ...currentMonthParts(),
      family_id: null,
      role_id: null,
    },
    monthlySummary: null,
    categoryDistribution: [],
    trendData: null,
    recentBills: [],
    collectionRecords: [],
    pendingAssignTotal: 0,
    uncategorizedTotal: 0,
    orphanTotal: 0,
    loading: false,
  }),

  getters: {
    currentMonth() {
      return formatMonth(this.filter.year, this.filter.month)
    },

    trendRange() {
      const now = new Date(this.filter.year, this.filter.month - 1, 1)
      const start = new Date(now)
      start.setMonth(start.getMonth() - 5)
      return {
        start_month: formatMonth(start.getFullYear(), start.getMonth() + 1),
        end_month: formatMonth(now.getFullYear(), now.getMonth() + 1),
      }
    },

    pendingCollectionCount() {
      return this.collectionRecords.filter(row => row.status === 'pending' || row.status === 'error').length
    },

    failedCollectionCount() {
      return this.collectionRecords.filter(row => row.status === 'error').length
    },

    todoItems() {
      return [
        {
          key: 'collection',
          label: '待解析采集记录',
          count: this.pendingCollectionCount,
          path: '/collection',
          level: this.failedCollectionCount > 0 ? 'danger' : 'warning',
        },
        {
          key: 'assign',
          label: '待分配账单',
          count: this.pendingAssignTotal,
          path: '/bills',
          query: { assign_status: 'pending' },
          level: 'warning',
        },
        {
          key: 'category',
          label: '未分类账单',
          count: this.uncategorizedTotal,
          path: '/bills',
          level: 'info',
        },
        {
          key: 'orphan',
          label: '待溯源记录',
          count: this.orphanTotal,
          path: '/accounting',
          level: 'primary',
        },
      ]
    },
  },

  actions: {
    async loadDashboard() {
      this.loading = true
      try {
        const params = {
          year: this.filter.year,
          month: this.filter.month,
          family_id: this.filter.family_id,
          role_id: this.filter.role_id,
        }
        const range = monthDateRange(this.filter.year, this.filter.month)
        const billScope = {
          ...range,
          family_id: this.filter.family_id,
          role_id: this.filter.role_id,
        }

        const [
          summary,
          distribution,
          trend,
          recent,
          collections,
          pendingAssign,
          orphans,
        ] = await Promise.all([
          call('get_monthly_summary', params),
          call('get_category_distribution', { ...params, direction: 'expense' }),
          call('get_trend_data', {
            ...this.trendRange,
            family_id: this.filter.family_id,
            role_id: this.filter.role_id,
          }),
          call('query_bills', { filters: billScope, page: 1, page_size: 6 }),
          call('get_collection_list', { page: 1, page_size: 8 }),
          call('query_bills', {
            filters: { assign_status: 'pending', ...range },
            page: 1,
            page_size: 1,
          }),
          call('get_orphan_records', { page: 1, page_size: 1 }).catch(() => ({ total: 0, list: [] })),
        ])

        this.monthlySummary = summary
        this.categoryDistribution = distribution.categories || []
        this.trendData = trend
        this.recentBills = recent.list || []
        this.collectionRecords = collections.list || []
        this.pendingAssignTotal = pendingAssign.total || 0
        this.uncategorizedTotal = null
        this.orphanTotal = orphans.total || 0
      } finally {
        this.loading = false
      }
    },

    setFilter(filter) {
      Object.assign(this.filter, filter)
      return this.loadDashboard()
    },
  },
})
