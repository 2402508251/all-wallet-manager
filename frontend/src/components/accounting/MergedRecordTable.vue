<template>
  <el-table :data="records" style="width: 100%" size="small" empty-text="暂无已合并记录">
    <el-table-column label="时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="渠道" width="70">
      <template #default="{ row }">
        <el-tag size="small" :type="channelTag(row.channel)">{{ channelLabel(row.channel) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="counterparty" label="对方" min-width="120" show-overflow-tooltip />
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        -¥{{ (row.amount_cents / 100).toFixed(2) }}
      </template>
    </el-table-column>
    <el-table-column label="真实支付者" min-width="120">
      <template #default="{ row }">
        <el-tag size="small" type="info">{{ row.real_payer_name || '未知账户' }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="120" fixed="right">
      <template #default="{ row }">
        <el-button link type="warning" size="small" @click="$emit('undo', row)">
          撤销合并
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
defineProps({
  records: { type: Array, default: () => [] },
})

defineEmits(['undo'])

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
