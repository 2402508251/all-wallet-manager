<template>
  <el-table :data="records" style="width: 100%" size="small" empty-text="暂无信用消费记录">
    <el-table-column label="时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="渠道" width="70">
      <template #default="{ row }">
        <el-tag size="small" :type="channelTag(row.channel)">
          {{ channelLabel(row.channel) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="counterparty" label="对方" min-width="120" show-overflow-tooltip />
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        <span class="amount-expense">-¥{{ (row.amount_cents / 100).toFixed(2) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="信用账户" width="100">
      <template #default="{ row }">
        {{ row.credit_account_name || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="关联状态" width="110">
      <template #default="{ row }">
        <el-tag size="small" :type="row.credit_account_id ? 'success' : 'warning'">
          {{ row.credit_account_id ? '已关联信用账户' : '待绑定账户' }}
        </el-tag>
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

function channelLabel(ch) {
  const map = { wechat: '微信', alipay: '支付宝', ccb: '建行' }
  return map[ch] || ch
}

function channelTag(ch) {
  const map = { wechat: 'success', alipay: 'primary', ccb: 'warning' }
  return map[ch] || 'info'
}
</script>
