<template>
  <el-table :data="pairs" style="width: 100%" size="small" empty-text="暂无自动配对记录">
    <el-table-column label="转出时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.out_trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="转出账户" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.out_counterparty || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="转入账户" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.in_counterparty || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        ¥{{ (row.out_amount_cents / 100).toFixed(2) }}
      </template>
    </el-table-column>
    <el-table-column label="配对依据" width="150">
      <template #default="{ row }">
        <el-tag size="small" type="success">{{ row.transfer_link_id ? '自动配对成功' : '已确认' }}</el-tag>
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
