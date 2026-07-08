<template>
  <el-table :data="candidates" size="small" empty-text="暂无待确认配对">
    <el-table-column label="转出时间" width="140">
      <template #default="{ row }">
        {{ formatDateTime(row.out_bill?.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="转出账户" min-width="160" show-overflow-tooltip>
      <template #default="{ row }">
        <div class="account-cell">
          <strong>{{ row.out_account_name || '-' }}</strong>
          <span>{{ row.out_counterparty || row.out_bill?.counterparty || '-' }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="转入候选账户" min-width="160" show-overflow-tooltip>
      <template #default="{ row }">
        <div class="account-cell">
          <strong>{{ row.in_account_name || '-' }}</strong>
          <span>{{ row.in_counterparty || row.in_bill?.counterparty || '-' }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        <span class="amount-expense">{{ formatSignedYuan(row.out_bill?.amount_cents || 0, 'expense') }}</span>
      </template>
    </el-table-column>
    <el-table-column label="匹配依据" width="150">
      <template #default="{ row }">
        <el-tag size="small" type="warning">{{ row.time_diff_minutes }} 分钟内</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="$emit('confirm', { outId: row.out_bill_id, inId: row.in_bill_id })">
          确认配对
        </el-button>
        <el-button link type="danger" size="small" @click="$emit('reject', { outId: row.out_bill_id, inId: row.in_bill_id })">
          拒绝
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { formatDateTime, formatSignedYuan } from '@/utils/formatters'

defineProps({
  candidates: { type: Array, default: () => [] },
})

defineEmits(['confirm', 'reject'])
</script>

<style scoped>
.account-cell {
  display: grid;
  gap: 2px;
}

.account-cell span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}
</style>
