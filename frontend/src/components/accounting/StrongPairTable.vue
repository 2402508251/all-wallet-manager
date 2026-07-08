<template>
  <el-table :data="pairs" size="small" empty-text="暂无自动配对记录">
    <el-table-column label="转出时间" width="140">
      <template #default="{ row }">
        {{ formatDateTime(row.out_trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="转出渠道" width="88">
      <template #default="{ row }">
        <el-tag size="small" :type="channelTag(row.out_channel)">
          {{ channelLabel(row.out_channel) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="转入渠道" width="88">
      <template #default="{ row }">
        <el-tag size="small" :type="channelTag(row.in_channel)">
          {{ channelLabel(row.in_channel) }}
        </el-tag>
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
        <span class="amount-expense">{{ formatSignedYuan(row.out_amount_cents || 0, 'expense') }}</span>
      </template>
    </el-table-column>
    <el-table-column label="配对依据" width="150">
      <template #default="{ row }">
        <el-tag size="small" type="success">{{ row.transfer_link_id ? '自动配对成功' : '已确认' }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="配对号" min-width="180" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.transfer_link_id || '-' }}
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
  pairs: { type: Array, default: () => [] },
})
</script>
