<template>
  <el-table :data="records" size="small" empty-text="暂无还款记录">
    <el-table-column label="时间" width="140">
      <template #default="{ row }">
        {{ formatDateTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="渠道" width="70">
      <template #default="{ row }">
        <el-tag size="small" :type="channelTag(row.channel)">
          {{ channelLabel(row.channel) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        <span class="amount-expense">{{ formatSignedYuan(row.amount_cents, 'expense') }}</span>
      </template>
    </el-table-column>
    <el-table-column label="还款来源" min-width="120">
      <template #default="{ row }">
        {{ row.payment_method || '-' }}
      </template>
    </el-table-column>
    <el-table-column prop="counterparty" label="对方" min-width="120" show-overflow-tooltip />
    <el-table-column label="信用账户" min-width="120" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.credit_account_name || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="镜像状态" width="100">
      <template #default="{ row }">
        <el-tag size="small" :type="row.transfer_link_id ? 'success' : 'warning'">
          {{ row.transfer_link_id ? '已生成' : '未生成' }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import {
  channelLabel,
  channelTag,
  formatDateTime,
  formatSignedYuan,
} from '@/utils/formatters'

defineProps({
  records: { type: Array, default: () => [] },
})
</script>
