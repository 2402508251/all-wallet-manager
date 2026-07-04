<template>
  <div class="chart-box">
    <h4 class="chart-title">月度收支柱状图</h4>
    <div ref="chartRef" class="chart-inner"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useECharts } from '@/composables/useECharts'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['bar-click'])

const chartRef = ref(null)

const chartOption = computed(() => {
  const summary = props.data || {}
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const items = params.map(p =>
          `${p.marker}${p.seriesName}: ¥${(p.value / 100).toLocaleString()}`
        )
        return items.join('<br/>')
      },
    },
    legend: {
      data: ['支出', '收入'],
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
      data: ['支出', '收入'],
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (v) => `¥${(v / 100).toFixed(0)}`,
      },
    },
    series: [
      {
        name: '支出',
        type: 'bar',
        data: [summary.expense || 0, 0],
        itemStyle: { color: '#f56c6c' },
        emphasis: { itemStyle: { color: '#e04545' } },
      },
      {
        name: '收入',
        type: 'bar',
        data: [0, summary.income || 0],
        itemStyle: { color: '#67c23a' },
        emphasis: { itemStyle: { color: '#4a9e28' } },
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
.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text-primary);
}
</style>
