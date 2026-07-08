// stores/report.js — 统计报表状态（筛选/摘要/分类/趋势）

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'

function formatMonth(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`
}

export const useReportStore = defineStore('report', {
  state: () => ({
    filter: {
      year: new Date().getFullYear(),
      month: new Date().getMonth() + 1,
      family_id: null,
      role_id: null,
    },
    hideRepayment: false,
    monthlySummary: null,
    categoryDistribution: [],
    trendData: null,
    loading: false,
  }),

  getters: {
    currentMonth() {
      return formatMonth(this.filter.year, this.filter.month)
    },

    dateRange() {
      const { year, month } = this.filter
      const start = formatMonth(year, month) + '-01'
      const endMonth = month === 12 ? 1 : month + 1
      const endYear = month === 12 ? year + 1 : year
      const end = formatMonth(endYear, endMonth) + '-01'
      return { start_time: start, end_time: end }
    },

    // 近 6 个月范围
    trendRange() {
      const now = new Date(this.filter.year, this.filter.month - 1, 1)
      const start = new Date(now)
      start.setMonth(start.getMonth() - 5)
      return {
        start_month: formatMonth(start.getFullYear(), start.getMonth() + 1),
        end_month: formatMonth(now.getFullYear(), now.getMonth() + 1),
      }
    },
  },

  actions: {
    async loadAllReports() {
      this.loading = true
      try {
        const params = {
          year: this.filter.year,
          month: this.filter.month,
          family_id: this.filter.family_id,
          role_id: this.filter.role_id,
          hide_internal: this.hideRepayment,
        }
        const trendParams = {
          ...this.trendRange,
          family_id: this.filter.family_id,
          role_id: this.filter.role_id,
          hide_internal: this.hideRepayment,
        }

        const [summary, distribution, trend] = await Promise.all([
          call('get_monthly_summary', params),
          call('get_category_distribution', {
            ...params,
            direction: 'expense',
          }),
          call('get_trend_data', trendParams),
        ])

        this.monthlySummary = summary
        this.categoryDistribution = distribution.categories || []
        this.trendData = trend
      } finally {
        this.loading = false
      }
    },

    setFilter(filter) {
      Object.assign(this.filter, filter)
      this.loadAllReports()
    },

    async toggleHideRepayment(hide) {
      this.hideRepayment = hide
      await call('toggle_hide_repayment_transfer', { hide })
      await this.loadAllReports()
    },
  },
})
