<template>
  <el-table :data="accounts" size="small" empty-text="暂无信用账户">
    <el-table-column prop="account_name" label="名称" min-width="120" />
    <el-table-column label="信用类型" width="110">
      <template #default="{ row }">
        <el-tag size="small">{{ creditTypeLabel(row.credit_type) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="关联还款账户" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">
        {{ row.linked_account_name || row.linked_account_id || '未关联' }}
      </template>
    </el-table-column>
    <el-table-column prop="role_name" label="归属角色" width="120">
      <template #default="{ row }">
        {{ row.role_name || '-' }}
      </template>
    </el-table-column>
    <el-table-column label="额度" width="120" align="right">
      <template #default="{ row }">
        {{ formatYuan(row.credit_limit_cents || 0) }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width="120" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="$emit('edit', row)">编辑</el-button>
        <el-button link type="danger" size="small" @click="$emit('delete', row)">删除</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { creditTypeLabel, formatYuan } from '@/utils/formatters'

defineProps({
  accounts: { type: Array, default: () => [] },
})

defineEmits(['edit', 'delete'])
</script>
