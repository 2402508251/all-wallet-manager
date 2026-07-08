<template>
  <div class="chart-box">
    <h4 class="chart-title">分类排行表</h4>
    <el-table :data="sortedData" style="width: 100%" size="small" empty-text="暂无数据"
      @row-click="handleRowClick"
    >
      <el-table-column label="排名" width="60" align="center">
        <template #default="{ $index }">
          <span :class="rankClass($index)">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分类" min-width="120">
        <template #default="{ row }">
          {{ row.category_name || '未分类' }}
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          {{ formatYuan(row.total_amount || 0) }}
        </template>
      </el-table-column>
      <el-table-column label="占比" width="80" align="right">
        <template #default="{ row }">
          {{ percentFor(row) }}%
        </template>
      </el-table-column>
      <el-table-column label="笔数" width="80" align="right">
        <template #default="{ row }">
          {{ row.count || 0 }} 笔
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const emit = defineEmits(['row-click'])

const sortedData = computed(() => {
  return [...props.data].sort((a, b) => (b.total_amount || 0) - (a.total_amount || 0))
})

const totalAmount = computed(() => {
  return sortedData.value.reduce((sum, item) => sum + (item.total_amount || 0), 0)
})

function percentFor(row) {
  if (!totalAmount.value) return '0.0'
  return ((row.total_amount || 0) / totalAmount.value * 100).toFixed(1)
}

function rankClass(index) {
  if (index === 0) return 'rank-1'
  if (index === 1) return 'rank-2'
  if (index === 2) return 'rank-3'
  return ''
}

function handleRowClick(row) {
  emit('row-click', row.category_name)
}
</script>

<style scoped>
.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
  color: var(--color-text-primary);
}

.rank-1 { color: #ff6b6b; font-weight: 700; }
.rank-2 { color: #ffa94d; font-weight: 600; }
.rank-3 { color: #ffd43b; font-weight: 600; }
</style>
