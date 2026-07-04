<template>
  <el-table :data="pairs" style="width: 100%" size="small" empty-text="暂无自动配对记录">
    <el-table-column label="转出时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="转入" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.counterparty || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        ¥{{ (row.amount_cents / 100).toFixed(2) }}
      </template>
    </el-table-column>
    <el-table-column label="配对依据" width="150">
      <template #default="{ row }">
        <el-tag size="small" type="success">备注单号一致</el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
defineProps({
  pairs: { type: Array, default: () => [] },
})

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 16).replace('T', ' ')
}
</script>
