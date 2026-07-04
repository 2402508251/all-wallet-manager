<template>
  <div class="chart-box">
    <h4 class="chart-title">分类支出饼图</h4>
    <div ref="chartRef" class="chart-inner"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useECharts } from '@/composables/useECharts'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const emit = defineEmits(['slice-click'])

const chartRef = ref(null)

const chartOption = computed(() => {
  const categories = props.data || []
  const pieData = categories.map(c => ({
    name: c.category_name || '未分类',
    value: c.total_amount || 0,
    icon: c.icon || '',
    count: c.count || 0,
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const d = params.data
        return `${params.marker}${params.name}<br/>金额: ¥${(params.value / 100).toLocaleString()}<br/>占比: ${params.percent}%<br/>笔数: ${d.count}`
      },
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 20,
      bottom: 20,
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 4,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
          },
        },
        data: pieData,
      },
    ],
  }
})

const { updateChart } = useECharts(chartRef, () => chartOption.value)

// 绑定点击事件
function bindClick() {
  if (chartRef.value) {
    const chart = chartRef.value._chartInstance
    if (chart) {
      chart.off('click')
      chart.on('click', (params) => {
        if (params.componentType === 'series') {
          const cat = props.data[params.dataIndex]
          if (cat) {
            emit('slice-click', cat.category_name)
          }
        }
      })
    }
  }
}

watch(() => props.data, () => {
  updateChart()
  setTimeout(bindClick, 100)
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
