// composables/useECharts.js — ECharts 通用封装

import { onMounted, onBeforeUnmount } from 'vue'
import { echarts } from '@/utils/echarts'

export function useECharts(chartRef, optionGetter) {
  let chart = null

  const initChart = () => {
    if (chartRef.value) {
      chart = echarts.init(chartRef.value)
      chart.setOption(optionGetter())
    }
  }

  const updateChart = () => {
    if (chart) chart.setOption(optionGetter())
  }

  const handleResize = () => chart?.resize()

  onMounted(() => {
    initChart()
    window.addEventListener('resize', handleResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    chart?.dispose()
  })

  return { updateChart, handleResize }
}
