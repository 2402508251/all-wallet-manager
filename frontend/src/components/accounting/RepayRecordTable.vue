<template>
  <el-table :data="records" style="width: 100%" size="small" empty-text="暂无还款记录">
    <el-table-column label="时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        <span class="amount-expense">-¥{{ (row.amount_cents / 100).toFixed(2) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="还款来源" min-width="120">
      <template #default="{ row }">
        {{ row.payment_method || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="信用账户" width="100">
      <template #default="{ row }">
        {{ row.credit_account_name || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="关联消费数" width="100">
      <template #default="{ row }">
        {{ row.transfer_link_id ? '已关联' : '未关联' }}
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
defineProps({
  records: { type: Array, default: () => [] },
})

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 16).replace('T', ' ')
}
</script>
