<template>
  <div class="chart-box">
    <div class="action-bar rank-toolbar">
      <h4 class="chart-title">{{ title }}</h4>
      <el-radio-group v-model="sortMode" size="small">
        <el-radio-button label="amount">按金额</el-radio-button>
        <el-radio-button label="count">按次数</el-radio-button>
      </el-radio-group>
    </div>
    <el-table
      :data="sortedData"
      style="width: 100%"
      size="small"
      empty-text="暂无数据"
      @row-click="handleRowClick"
    >
      <el-table-column label="排名" width="60" align="center">
        <template #default="{ $index }">
          <span :class="rankClass($index)">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分类" min-width="120">
        <template #default="{ row }">
          {{ row[labelField] || row.category_name || row.label || '未分类' }}
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          {{ formatYuan(row.total_amount || 0) }}
        </template>
      </el-table-column>
      <el-table-column label="金额占比" width="90" align="right">
        <template #default="{ row }">
          {{ amountPercentFor(row) }}%
        </template>
      </el-table-column>
      <el-table-column label="笔数" width="80" align="right">
        <template #default="{ row }">
          {{ row.count || 0 }} 笔
        </template>
      </el-table-column>
      <el-table-column label="次数占比" width="90" align="right">
        <template #default="{ row }">
          {{ countPercentFor(row) }}%
        </template>
      </el-table-column>
      <el-table-column v-if="showAverage" label="均笔金额" width="110" align="right">
        <template #default="{ row }">
          {{ formatYuan(row.avg_amount || 0) }}
        </template>
      </el-table-column>
      <el-table-column v-if="showChange" label="较上期金额" width="120" align="right">
        <template #default="{ row }">
          <span :class="changeClass(row.amount_delta)">
            {{ deltaText(row.amount_delta) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column v-if="showChange" label="较上期占比" width="100" align="right">
        <template #default="{ row }">
          <span :class="changeClass(row.amount_delta)">
            {{ ratioText(row.amount_change_ratio) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Array, default: () => [] },
  title: { type: String, default: '分类排行表' },
  labelField: { type: String, default: 'category_name' },
  showAverage: { type: Boolean, default: false },
  showChange: { type: Boolean, default: false },
})

const emit = defineEmits(['row-click', 'item-click'])
const sortMode = ref('amount')

const sortedData = computed(() => {
  const list = [...props.data]
  if (sortMode.value === 'count') {
    return list.sort((a, b) => {
      if ((b.count || 0) !== (a.count || 0)) return (b.count || 0) - (a.count || 0)
      return (b.total_amount || 0) - (a.total_amount || 0)
    })
  }
  return list.sort((a, b) => {
    if ((b.total_amount || 0) !== (a.total_amount || 0)) return (b.total_amount || 0) - (a.total_amount || 0)
    return (b.count || 0) - (a.count || 0)
  })
})

const totalAmount = computed(() => {
  return sortedData.value.reduce((sum, item) => sum + (item.total_amount || 0), 0)
})

const totalCount = computed(() => {
  return sortedData.value.reduce((sum, item) => sum + (item.count || 0), 0)
})

function amountPercentFor(row) {
  if (!totalAmount.value) return '0.0'
  return ((row.total_amount || 0) / totalAmount.value * 100).toFixed(1)
}

function countPercentFor(row) {
  if (!totalCount.value) return '0.0'
  return (((row.count || 0) / totalCount.value) * 100).toFixed(1)
}

function rankClass(index) {
  if (index === 0) return 'rank-1'
  if (index === 1) return 'rank-2'
  if (index === 2) return 'rank-3'
  return ''
}

function handleRowClick(row) {
  emit('row-click', row[props.labelField] || row.category_name || row.label)
  emit('item-click', row)
}

function deltaText(value) {
  if (value === null || value === undefined) return '无历史'
  if (value === 0) return '持平'
  const amount = formatYuan(Math.abs(value))
  return value > 0 ? `+${amount}` : `-${amount}`
}

function ratioText(value) {
  if (value === null || value === undefined) return '无历史'
  if (value === 0) return '持平'
  const percent = `${Math.abs(value * 100).toFixed(1)}%`
  return value > 0 ? `+${percent}` : `-${percent}`
}

function changeClass(value) {
  if (value > 0) return 'amount-expense'
  if (value < 0) return 'amount-income'
  return ''
}
</script>

<style scoped>
.rank-toolbar {
  align-items: center;
}

.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.rank-1 { color: #ff6b6b; font-weight: 700; }
.rank-2 { color: #ffa94d; font-weight: 600; }
.rank-3 { color: #ffd43b; font-weight: 600; }
</style>
