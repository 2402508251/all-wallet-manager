<template>
  <div class="page-container">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Reports</div>
        <h2 class="page-title">月度统计报表</h2>
        <p class="page-subtitle">查看收支摘要、分类分布、近 6 个月趋势，并下钻到对应账单明细。</p>
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
      <SummaryCard :summary="reportStore.monthlySummary" />

      <div class="chart-row">
        <MonthlyBarChart :data="reportStore.monthlySummary" />
        <CategoryPieChart
          :data="reportStore.categoryDistribution"
          @slice-click="handleCategoryClick"
        />
      </div>

      <TrendLineChart :data="reportStore.trendData" />

      <CategoryRankTable
        :data="reportStore.categoryDistribution"
        @row-click="handleCategoryClick"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useReportStore } from '@/stores/report'
import { useSystemStore } from '@/stores/system'
import ReportFilter from '@/components/report/ReportFilter.vue'
import SummaryCard from '@/components/report/SummaryCard.vue'
import MonthlyBarChart from '@/components/report/MonthlyBarChart.vue'
import CategoryPieChart from '@/components/report/CategoryPieChart.vue'
import TrendLineChart from '@/components/report/TrendLineChart.vue'
import CategoryRankTable from '@/components/report/CategoryRankTable.vue'

const reportStore = useReportStore()
const systemStore = useSystemStore()
const router = useRouter()

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

function handleCategoryClick(categoryName) {
  // 查找 category_id
  const cat = systemStore.categories.find(c => c.name === categoryName)
  const { start_time, end_time } = reportStore.dateRange
  const query = {
    category_id: cat?.id || '',
    direction: 'expense',
    start_time,
    end_time,
  }
  if (reportStore.filter.family_id) query.family_id = reportStore.filter.family_id
  if (reportStore.filter.role_id) query.role_id = reportStore.filter.role_id

  router.push({
    path: '/bills',
    query,
  })
}
</script>

<style scoped>
.report-content {
  min-height: 400px;
}
</style>
