<template>
  <div class="page-container">
    <h2 class="page-title">统计报表</h2>

    <!-- 筛选 -->
    <ReportFilter
      :filter="reportStore.filter"
      :hide-repayment="reportStore.hideRepayment"
      :families="systemStore.families"
      :roles="systemStore.roles"
      @update:filter="handleFilterChange"
      @toggle-repayment="handleToggleRepayment"
    />

    <!-- 加载中 -->
    <div v-loading="reportStore.loading" class="report-content">
      <!-- 月度摘要卡片 -->
      <SummaryCard :summary="reportStore.monthlySummary" />

      <!-- 图表区域 -->
      <div class="chart-row">
        <MonthlyBarChart :data="reportStore.monthlySummary" />
        <CategoryPieChart
          :data="reportStore.categoryDistribution"
          @slice-click="handleCategoryClick"
        />
      </div>

      <!-- 趋势图 -->
      <TrendLineChart :data="reportStore.trendData" />

      <!-- 分类排行表 -->
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
    reportStore.loadAllReports(),
  ])
})

function handleFilterChange(filter) {
  reportStore.setFilter(filter)
  if (filter.family_id !== undefined) {
    systemStore.loadRoles(filter.family_id)
  }
}

function handleToggleRepayment(hide) {
  reportStore.toggleHideRepayment(hide)
}

function handleCategoryClick(categoryName) {
  // 查找 category_id
  const cat = systemStore.categories.find(c => c.name === categoryName)
  const { start_time, end_time } = reportStore.dateRange

  router.push({
    path: '/bills',
    query: {
      category_id: cat?.id || '',
      direction: 'expense',
      start_time,
      end_time,
    },
  })
}
</script>

<style scoped>
.report-content {
  min-height: 400px;
}
</style>
