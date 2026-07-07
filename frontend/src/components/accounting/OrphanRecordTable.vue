<template>
  <div>
    <el-table :data="records" style="width: 100%" size="small" empty-text="暂无待溯源记录">
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
      <el-table-column prop="payment_method" label="支付方式" width="100" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="success" size="small" @click="$emit('merge', row)">
            尝试溯源
          </el-button>
          <el-button link type="primary" size="small" @click="$emit('confirm', row)">
            确认独立计入
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > 0" style="margin-top:12px;text-align:right">
      <el-pagination
        small
        layout="prev, pager, next"
        :total="total"
        :page-size="20"
        @current-change="(p) => $emit('page-change', p)"
      />
    </div>
  </div>
</template>

<script setup>
defineProps({
  records: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
})

defineEmits(['confirm', 'merge', 'page-change'])

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
