// composables/useECharts.js — ECharts 通用封装

import { onMounted, onBeforeUnmount, shallowRef } from 'vue'
import { echarts } from '@/utils/echarts'

export function useECharts(chartRef, optionGetter) {
  let chart = null
  let resizeObserver = null
  const chartInstance = shallowRef(null)

  const initChart = () => {
    if (chartRef.value) {
      chart = echarts.init(chartRef.value)
      chartInstance.value = chart
      chart.setOption(optionGetter())
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(() => handleResize())
        resizeObserver.observe(chartRef.value)
      }
    }
  }

  const updateChart = () => {
    if (chart) chart.setOption(optionGetter(), true)
  }

  const handleResize = () => chart?.resize()
  const getChart = () => chart

  onMounted(() => {
    initChart()
    window.addEventListener('resize', handleResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    resizeObserver?.disconnect()
    chart?.dispose()
    chart = null
    chartInstance.value = null
  })

  return { updateChart, handleResize, getChart, chartInstance }
}
