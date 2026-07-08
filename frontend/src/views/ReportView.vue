<template>
  <div class="page-container report-page">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Reports</div>
        <h2 class="page-title">综合统计报表</h2>
        <p class="page-subtitle">从总览、趋势、分类、维度和账务健康多个角度复盘财务数据，并继续下钻到账单明细。</p>
      </div>
    </section>

    <ReportFilter
      :filter="reportStore.filter"
      :hide-repayment="reportStore.hideRepayment"
      :families="systemStore.families"
      :roles="systemStore.roles"
      @update:filter="handleFilterChange"
      @toggle-repayment="handleToggleRepayment"
    />

    <div v-loading="reportStore.loading" class="report-content">
      <SummaryCard :overview="reportStore.overview" />

      <div class="chart-row">
        <MonthlyBarChart :data="barSummary" title="当前范围收支对比" />
        <TrendLineChart
          :data="{ months: reportStore.trendOverview, granularity: reportStore.trendGranularity }"
          :title="trendTitle"
        />
      </div>

      <ExpenseCategorySummary
        :summary="reportStore.categoryExpenseInsight"
        @uncategorized-click="handleUncategorizedClick"
      />

      <div class="chart-row category-focus-row">
        <CategoryPieChart
          title="支出分类分布"
          :data="reportStore.categoryExpenseStats"
          enhanced
          @item-click="handleDimensionClick('category', $event, { direction: 'expense' })"
        />
        <CategoryRankTable
          title="支出分类排行"
          :data="reportStore.categoryExpenseStats"
          label-field="label"
          :show-average="true"
          :show-change="true"
          @item-click="handleDimensionClick('category', $event, { direction: 'expense' })"
        />
      </div>

      <div class="chart-row">
        <CategoryPieChart
          title="收入分类分布"
          :data="reportStore.categoryIncomeStats"
          @item-click="handleDimensionClick('category', $event, { direction: 'income' })"
        />
      </div>

      <div class="report-section-grid">
        <DailyCalendarPanel
          v-if="reportStore.showCalendar"
          :data="calendarForView"
          @day-click="handleDayClick"
        />
        <ReportHealthPanel
          :health="reportStore.health"
          @item-click="handleHealthClick"
        />
      </div>

      <section class="surface-box rank-section">
        <div class="action-bar rank-header">
          <div>
            <div class="section-title">多维排行</div>
            <div class="section-subtitle">切换不同维度，查看金额、占比和笔数结构</div>
          </div>
        </div>

        <el-tabs v-model="activeRankTab">
          <el-tab-pane label="分类" name="category">
            <CategoryRankTable
              title="支出分类明细排行"
              :data="reportStore.categoryExpenseStats"
              label-field="label"
              :show-average="true"
              :show-change="true"
              @item-click="handleDimensionClick('category', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
          <el-tab-pane label="账户" name="account">
            <CategoryRankTable
              title="账户支出排行"
              :data="reportStore.accountExpenseStats"
              label-field="label"
              @item-click="handleDimensionClick('account', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
          <el-tab-pane label="角色" name="role">
            <CategoryRankTable
              title="角色支出排行"
              :data="reportStore.roleExpenseStats"
              label-field="label"
              @item-click="handleDimensionClick('role', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
          <el-tab-pane label="渠道" name="channel">
            <CategoryRankTable
              title="渠道支出排行"
              :data="channelStats"
              label-field="label"
              @item-click="handleDimensionClick('channel', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
          <el-tab-pane label="交易类型" name="trade_type">
            <CategoryRankTable
              title="交易类型排行"
              :data="tradeTypeStats"
              label-field="label"
              @item-click="handleDimensionClick('trade_type', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
          <el-tab-pane label="交易对方" name="counterparty">
            <CategoryRankTable
              title="交易对方排行"
              :data="reportStore.counterpartyExpenseStats"
              label-field="label"
              @item-click="handleDimensionClick('counterparty', $event, { direction: 'expense' })"
            />
          </el-tab-pane>
        </el-tabs>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useReportStore } from '@/stores/report'
import { useSystemStore } from '@/stores/system'
import ReportFilter from '@/components/report/ReportFilter.vue'
import SummaryCard from '@/components/report/SummaryCard.vue'
import MonthlyBarChart from '@/components/report/MonthlyBarChart.vue'
import CategoryPieChart from '@/components/report/CategoryPieChart.vue'
import TrendLineChart from '@/components/report/TrendLineChart.vue'
import CategoryRankTable from '@/components/report/CategoryRankTable.vue'
import DailyCalendarPanel from '@/components/report/DailyCalendarPanel.vue'
import ReportHealthPanel from '@/components/report/ReportHealthPanel.vue'
import ExpenseCategorySummary from '@/components/report/ExpenseCategorySummary.vue'
import { channelLabel, tradeTypeLabel } from '@/utils/formatters'

const reportStore = useReportStore()
const systemStore = useSystemStore()
const router = useRouter()
const activeRankTab = ref('category')

const barSummary = computed(() => reportStore.overview?.summary || {})
const trendTitle = computed(() => {
  if (reportStore.filter.period === 'year') return `${reportStore.filter.year} 年月度收支趋势`
  if (reportStore.filter.period === 'custom') {
    return reportStore.trendGranularity === 'day'
      ? `${reportStore.filter.start_date} 至 ${reportStore.filter.end_date} 日度收支趋势`
      : `${reportStore.filter.start_date} 至 ${reportStore.filter.end_date} 月度收支趋势`
  }
  return `近 12 个月收支趋势（截至 ${reportStore.currentMonth}）`
})

const channelStats = computed(() => {
  return reportStore.channelExpenseStats.map(item => ({
    ...item,
    label: channelLabel(item.label),
  }))
})

const tradeTypeStats = computed(() => {
  return reportStore.tradeTypeExpenseStats.map(item => ({
    ...item,
    label: tradeTypeLabel(item.label),
  }))
})

const calendarForView = computed(() => {
  if (reportStore.showCalendar) return reportStore.dailyCalendar
  return []
})

onMounted(async () => {
  await Promise.all([
    systemStore.loadFamilies(),
    systemStore.loadRoles(null),
    systemStore.loadCategories(),
    reportStore.loadAllReports(),
  ])
})

async function handleFilterChange(filter) {
  if (Object.prototype.hasOwnProperty.call(filter, 'family_id')) {
    await systemStore.loadRoles(filter.family_id || null)
  }
  reportStore.setFilter(filter)
}

function handleToggleRepayment(hide) {
  reportStore.toggleHideRepayment(hide)
}

function handleUncategorizedClick() {
  router.push({
    path: '/bills',
    query: baseBillQuery({
      direction: 'expense',
      is_uncategorized: 1,
    }),
  })
}

function baseBillQuery(extra = {}) {
  const query = {
    ...reportStore.dateRange,
    ...extra,
  }
  if (reportStore.filter.family_id) query.family_id = reportStore.filter.family_id
  if (reportStore.filter.role_id) query.role_id = reportStore.filter.role_id
  return query
}

function handleDayClick(item) {
  router.push({
    path: '/bills',
    query: baseBillQuery({
      start_time: `${item.date}T00:00:00+08:00`,
      end_time: `${item.date}T23:59:59+08:00`,
    }),
  })
}

function handleHealthClick(item) {
  const healthQueryMap = {
    pending_assign: { assign_status: 'pending' },
    uncategorized: { is_uncategorized: 1 },
    orphan: { merge_status: 'orphan' },
    credit: { trade_type: 'credit_consumption' },
    repayment: { trade_type: 'repayment' },
    internal_transfer: { is_internal_flow: 1 },
  }
  router.push({
    path: '/bills',
    query: item.key === 'deleted'
      ? { ...baseBillQuery(), recycle: 1 }
      : baseBillQuery(healthQueryMap[item.key] || {}),
  })
}

function handleDimensionClick(dimension, item, extra = {}) {
  const query = baseBillQuery(extra)
  if (dimension === 'category') {
    if (item.key === '__other__') return
    if (item.label === '未分类' || item.key === null || item.key === undefined) query.is_uncategorized = 1
    else {
      const category = systemStore.categories.find(entry => entry.name === item.label)
      if (category?.id) query.category_id = category.id
    }
  } else if (dimension === 'account' && item.key && item.key !== '0') {
    query.account_id = item.key
  } else if (dimension === 'role' && item.key && item.key !== '0') {
    query.role_id = item.key
  } else if (dimension === 'channel' && item.key) {
    query.channel = item.key
  } else if (dimension === 'trade_type' && item.key) {
    query.trade_type = item.key
  } else if (dimension === 'counterparty' && item.label) {
    query.keyword = item.label
  }
  router.push({ path: '/bills', query })
}
</script>

<style scoped>
.report-page {
  padding-bottom: var(--spacing-lg);
}

.report-content {
  min-height: 480px;
  display: grid;
  gap: var(--spacing-md);
}

.report-section-grid {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: var(--spacing-md);
}

.rank-section {
  padding: var(--spacing-md);
}

.rank-header {
  margin-bottom: var(--spacing-sm);
}

.category-focus-row {
  grid-template-columns: minmax(360px, 1fr) minmax(460px, 1.2fr);
}

@media (max-width: 1200px) {
  .report-section-grid {
    grid-template-columns: 1fr;
  }

  .category-focus-row {
    grid-template-columns: 1fr;
  }
}
</style>
