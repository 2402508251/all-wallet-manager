<template>
  <div class="chart-box trend-chart">
    <h4 class="chart-title">消费趋势折线图 (近6个月)</h4>
    <div ref="chartRef" class="chart-inner"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useECharts } from '@/composables/useECharts'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const chartRef = ref(null)

const chartOption = computed(() => {
  const d = props.data || {}
  const months = d.months || []
  const income = d.income || []
  const expense = d.expense || []

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
      data: ['月支出', '月收入'],
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
    series: [
      {
        name: '月支出',
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
        name: '月收入',
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
    ],
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
