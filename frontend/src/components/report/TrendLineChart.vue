<template>
  <div class="chart-box trend-chart">
    <h4 class="chart-title">{{ title }}</h4>
    <div ref="chartRef" class="chart-inner"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useECharts } from '@/composables/useECharts'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  title: { type: String, default: '趋势折线图' },
})

const chartRef = ref(null)

const chartOption = computed(() => {
  const d = props.data || {}
  const granularity = d.granularity === 'day' ? 'day' : 'month'
  const unitLabel = granularity === 'day' ? '日' : '月'
  const hasStructuredMonths = Array.isArray(d.months) && d.months.length > 0 && typeof d.months[0] === 'object'
  const months = hasStructuredMonths ? d.months.map(item => item.label || item.month) : (d.months || [])
  const income = hasStructuredMonths ? d.months.map(item => item.income || 0) : (d.income || [])
  const expense = hasStructuredMonths ? d.months.map(item => item.expense || 0) : (d.expense || [])
  const net = hasStructuredMonths ? d.months.map(item => item.net || 0) : (d.net || [])

  const series = [
    {
      name: `${unitLabel}支出`,
      type: 'line',
      data: expense,
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: { color: '#f56c6c' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(245,108,108,0.3)' },
            { offset: 1, color: 'rgba(245,108,108,0.02)' },
          ],
        },
      },
    },
    {
      name: `${unitLabel}收入`,
      type: 'line',
      data: income,
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: { color: '#67c23a' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(103,194,58,0.3)' },
            { offset: 1, color: 'rgba(103,194,58,0.02)' },
          ],
        },
      },
    },
  ]

  if (net.length) {
    series.push({
      name: `${unitLabel}结余`,
      type: 'line',
      data: net,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: { color: '#1d4ed8' },
      lineStyle: { width: 2, type: 'dashed' },
    })
  }

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        let html = `${params[0].axisValue}<br/>`
        params.forEach(p => {
          html += `${p.marker}${p.seriesName}: ${formatYuan(p.value)}<br/>`
        })
        return html
      },
    },
    legend: {
      data: series.map(item => item.name),
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '35px',
      top: '10px',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: months,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (v) => formatYuan(v, { withSymbol: false }),
      },
    },
    series,
  }
})

const { updateChart } = useECharts(chartRef, () => chartOption.value)

watch(() => props.data, () => {
  updateChart()
}, { deep: true })
</script>

<style scoped>
.trend-chart {
  grid-column: 1 / -1;
}

.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text-primary);
}
</style>
