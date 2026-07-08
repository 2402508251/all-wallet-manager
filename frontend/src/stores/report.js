// stores/report.js — 综合统计报表状态

import { defineStore } from 'pinia'
import { call } from '@/utils/bridge'

function formatMonth(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`
}

function shiftMonth(year, month, delta) {
  const totalMonths = year * 12 + (month - 1) + delta
  return {
    year: Math.floor(totalMonths / 12),
    month: (totalMonths % 12) + 1,
  }
}

function monthBounds(year, month) {
  const start = `${formatMonth(year, month)}-01`
  const next = shiftMonth(year, month, 1)
  const end = `${formatMonth(next.year, next.month)}-01`
  return { start_time: start, end_time: end }
}

function formatDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-')
}

function todayRange() {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1
  return {
    start_date: `${formatMonth(year, month)}-01`,
    end_date: formatDate(new Date(year, month, 0)),
  }
}

function nextDate(dateString) {
  const date = new Date(`${dateString}T00:00:00`)
  date.setDate(date.getDate() + 1)
  return formatDate(date)
}

function sameMonth(startDate, endDate) {
  return String(startDate || '').slice(0, 7) === String(endDate || '').slice(0, 7)
}

const defaultCustomRange = todayRange()

export const useReportStore = defineStore('report', {
  state: () => ({
    filter: {
      period: 'month',
      year: new Date().getFullYear(),
      month: new Date().getMonth() + 1,
      start_date: defaultCustomRange.start_date,
      end_date: defaultCustomRange.end_date,
      family_id: null,
      role_id: null,
    },
    hideRepayment: false,
    overview: null,
    categoryExpenseInsight: null,
    categoryExpenseStats: [],
    categoryIncomeStats: [],
    accountExpenseStats: [],
    roleExpenseStats: [],
    channelExpenseStats: [],
    tradeTypeExpenseStats: [],
    counterpartyExpenseStats: [],
    trendOverview: [],
    trendGranularity: 'month',
    dailyCalendar: [],
    health: null,
    loading: false,
  }),

  getters: {
    currentMonth() {
      return formatMonth(this.filter.year, this.filter.month)
    },

    periodLabel() {
      if (this.filter.period === 'year') return `${this.filter.year} 年`
      if (this.filter.period === 'recent12') return `截至 ${this.currentMonth} 的近 12 个月`
      if (this.filter.period === 'custom') return `${this.filter.start_date} 至 ${this.filter.end_date}`
      return `${this.currentMonth}`
    },

    dateRange() {
      const { year, month, period } = this.filter
      if (period === 'year') {
        return {
          start_time: `${year}-01-01`,
          end_time: `${year + 1}-01-01`,
        }
      }
      if (period === 'recent12') {
        const start = shiftMonth(year, month, -11)
        return {
          start_time: `${formatMonth(start.year, start.month)}-01`,
          end_time: `${formatMonth(shiftMonth(year, month, 1).year, shiftMonth(year, month, 1).month)}-01`,
        }
      }
      if (period === 'custom') {
        return {
          start_time: `${this.filter.start_date}T00:00:00+08:00`,
          end_time: `${nextDate(this.filter.end_date)}T00:00:00+08:00`,
        }
      }
      return monthBounds(year, month)
    },

    trendRequest() {
      const { year, month, period } = this.filter
      if (period === 'custom') {
        return {
          period: 'custom',
          start_date: this.filter.start_date,
          end_date: this.filter.end_date,
        }
      }
      if (period === 'year') {
        return {
          end_year: year,
          end_month: 12,
          months: 12,
        }
      }
      return {
        end_year: year,
        end_month: month,
        months: 12,
      }
    },

    showCalendar() {
      if (this.filter.period === 'month') return true
      if (this.filter.period !== 'custom') return false
      return sameMonth(this.filter.start_date, this.filter.end_date)
    },
  },

  actions: {
    buildBaseParams() {
      const base = {
        period: this.filter.period,
        family_id: this.filter.family_id,
        role_id: this.filter.role_id,
        hide_internal: this.hideRepayment,
      }
      if (this.filter.period === 'custom') {
        base.start_date = this.filter.start_date
        base.end_date = this.filter.end_date
      } else {
        base.year = this.filter.year
        base.month = this.filter.month
      }
      return base
    },

    async loadAllReports() {
      this.loading = true
      try {
        const params = this.buildBaseParams()
        const [overview, expenseCategoryInsight, incomeCategories, accounts, roles, channels, tradeTypes, counterparties, trend, dailyCalendar, health] = await Promise.all([
          call('get_report_overview', params),
          call('get_report_category_insights', params),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'category',
            direction: 'income',
            limit: 8,
          }),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'account',
            direction: 'expense',
          }),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'role',
            direction: 'expense',
          }),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'channel',
            direction: 'expense',
          }),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'trade_type',
            direction: 'expense',
          }),
          call('get_report_dimension_stats', {
            ...params,
            dimension: 'counterparty',
            direction: 'expense',
          }),
          call('get_report_trend_overview', {
            ...this.trendRequest,
            family_id: this.filter.family_id,
            role_id: this.filter.role_id,
            hide_internal: this.hideRepayment,
          }),
          call('get_report_daily_calendar', params),
          call('get_report_accounting_health', params),
        ])

        this.overview = overview
        this.categoryExpenseInsight = expenseCategoryInsight.summary || null
        this.categoryExpenseStats = expenseCategoryInsight.items || []
        this.categoryIncomeStats = incomeCategories.items || []
        this.accountExpenseStats = accounts.items || []
        this.roleExpenseStats = roles.items || []
        this.channelExpenseStats = channels.items || []
        this.tradeTypeExpenseStats = tradeTypes.items || []
        this.counterpartyExpenseStats = counterparties.items || []
        this.trendOverview = trend.months || []
        this.trendGranularity = trend.granularity || 'month'
        this.dailyCalendar = dailyCalendar.days || []
        this.health = health
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
