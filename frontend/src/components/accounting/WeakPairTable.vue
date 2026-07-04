<template>
  <el-table :data="candidates" style="width: 100%" size="small" empty-text="暂无待确认配对">
    <el-table-column label="转出时间" width="140">
      <template #default="{ row }">
        {{ formatTime(row.trade_time) }}
      </template>
    </el-table-column>
    <el-table-column label="转入候选" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.counterparty || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="金额" width="100" align="right">
      <template #default="{ row }">
        ¥{{ (row.amount_cents / 100).toFixed(2) }}
      </template>
    </el-table-column>
    <el-table-column label="匹配度" width="140">
      <template #default="{ row }">
        <el-tag size="small" type="warning">弱匹配</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="$emit('confirm', { outId: row.id, inId: row.candidate_id })">
          确认配对
        </el-button>
        <el-button link type="danger" size="small" @click="$emit('reject', row.id)">
          拒绝
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
defineProps({
  candidates: { type: Array, default: () => [] },
})

defineEmits(['confirm', 'reject'])

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 16).replace('T', ' ')
}
</script>
