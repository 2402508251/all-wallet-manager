<template>
  <div v-if="bill" class="accounting-info">
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="溯源状态">
        <el-tag size="small" :type="mergeStatusType(mergeStatus)">
          {{ mergeStatusLabel(mergeStatus) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="信用消费">
        <el-tag size="small" :type="bill.is_credit ? 'warning' : 'info'">
          {{ bill.is_credit ? '是' : '否' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item v-if="bill.credit_account_id" label="信用账户">
        {{ bill.credit_account_name || `账户#${bill.credit_account_id}` }}
      </el-descriptions-item>
      <el-descriptions-item label="转账配对号">
        <span class="long-text">{{ bill.transfer_link_id || '未配对' }}</span>
      </el-descriptions-item>
      <el-descriptions-item v-if="bill.merged_group_id" label="溯源组ID">
        <span class="long-text">{{ bill.merged_group_id }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="分配状态">
        <el-tag size="small" :type="assignStatusType(bill.assign_status)">
          {{ assignStatusLabel(bill.assign_status) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="系统生成">
        <el-tag size="small" :type="bill.is_system ? 'danger' : 'info'">
          {{ bill.is_system ? '是' : '否' }}
        </el-tag>
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  bill: { type: Object, default: null },
})

const mergeStatus = computed(() => props.bill?.merge_status || 'normal')

function mergeStatusLabel(status) {
  const map = {
    normal: '正常',
    orphan: '待溯源',
    merged_source: '已溯源（发起方）',
    merged_target: '已溯源（真实支付者）',
  }
  return map[status] || status
}

function mergeStatusType(status) {
  const map = {
    normal: 'success',
    orphan: 'warning',
    merged_source: 'info',
    merged_target: 'primary',
  }
  return map[status] || 'info'
}

function assignStatusLabel(status) {
  const map = {
    assigned: '已分配',
    pending: '待分配',
    unassigned: '未分配',
  }
  return map[status] || status || '未分配'
}

function assignStatusType(status) {
  const map = {
    assigned: 'success',
    pending: 'warning',
    unassigned: 'info',
  }
  return map[status] || 'info'
}
</script>

<style scoped>
.accounting-info {
  padding: var(--spacing-sm);
}

.long-text {
  font-size: 12px;
  word-break: break-all;
}
</style>
