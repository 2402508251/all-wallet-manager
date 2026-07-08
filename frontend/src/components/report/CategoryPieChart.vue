<template>
  <div class="chart-box">
    <div class="action-bar chart-toolbar">
      <h4 class="chart-title">{{ title }}</h4>
      <div v-if="enhanced" class="chart-actions">
        <el-radio-group v-model="metricMode" size="small">
          <el-radio-button label="amount">按金额</el-radio-button>
          <el-radio-button label="count">按笔数</el-radio-button>
        </el-radio-group>
        <el-segmented v-model="topN" size="small" :options="topOptions" />
      </div>
    </div>
    <div ref="chartRef" class="chart-inner"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useECharts } from '@/composables/useECharts'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Array, default: () => [] },
  title: { type: String, default: '分类支出饼图' },
  enhanced: { type: Boolean, default: false },
})

const emit = defineEmits(['slice-click', 'item-click'])

const chartRef = ref(null)
const metricMode = ref('amount')
const topN = ref(5)
const topOptions = [
  { label: 'Top5', value: 5 },
  { label: 'Top10', value: 10 },
  { label: '全部', value: 999 },
]

const displayItems = computed(() => {
  const categories = [...(props.data || [])]
  if (!props.enhanced) return categories
  if (topN.value >= categories.length) return categories

  const visible = categories.slice(0, topN.value)
  const rest = categories.slice(topN.value)
  const otherAmount = rest.reduce((sum, item) => sum + (item.total_amount || 0), 0)
  const otherCount = rest.reduce((sum, item) => sum + (item.count || 0), 0)
  if (!rest.length) return visible

  visible.push({
    key: '__other__',
    label: '其他',
    total_amount: otherAmount,
    count: otherCount,
    ratio: rest.reduce((sum, item) => sum + (item.ratio || 0), 0),
    count_ratio: rest.reduce((sum, item) => sum + (item.count_ratio || 0), 0),
  })
  return visible
})

const chartOption = computed(() => {
  const categories = displayItems.value
  const pieData = categories.map(c => ({
    name: c.label || c.category_name || '未分类',
    value: metricMode.value === 'count' ? (c.count || 0) : (c.total_amount || 0),
    icon: c.icon || '',
    count: c.count || 0,
    amount: c.total_amount || 0,
    ratio: c.ratio || 0,
    count_ratio: c.count_ratio || 0,
  }))

  return {
    color: ['#1d4ed8', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#4b5563'],
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const d = params.data
        const primary = metricMode.value === 'count'
          ? `笔数: ${params.value} 笔`
          : `金额: ${formatYuan(params.value)}`
        return `${params.marker}${params.name}<br/>${primary}<br/>金额: ${formatYuan(d.amount)}<br/>笔数: ${d.count} 笔<br/>金额占比: ${((d.ratio || 0) * 100).toFixed(1)}%<br/>次数占比: ${((d.count_ratio || 0) * 100).toFixed(1)}%`
      },
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 20,
      bottom: 20,
      formatter: (name) => {
        const item = pieData.find(entry => entry.name === name)
        if (!item) return name
        return `${name}  ${formatYuan(item.amount)} / ${((item.ratio || 0) * 100).toFixed(1)}%`
      },
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

const { updateChart, getChart } = useECharts(chartRef, () => chartOption.value)

// 绑定点击事件
function bindClick() {
  const chart = getChart()
  if (!chart) return
      chart.off('click')
  chart.on('click', (params) => {
    if (params.componentType === 'series') {
      const cat = displayItems.value[params.dataIndex]
      if (cat) {
        emit('slice-click', cat.category_name || cat.label)
        emit('item-click', cat)
      }
    }
  })
}

watch(() => props.data, () => {
  updateChart()
  nextTick(bindClick)
}, { deep: true })
</script>

<style scoped>
.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.chart-toolbar {
  align-items: center;
  gap: var(--spacing-sm);
}

.chart-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
</style>
