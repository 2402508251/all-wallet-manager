<template>
  <div v-if="bill" class="bill-info">
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="交易时间">
        {{ formatTime(bill.trade_time) }}
      </el-descriptions-item>
      <el-descriptions-item label="交易类型">
        <el-tag size="small">{{ tradeTypeLabel(bill.trade_type) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="交易对方">
        {{ bill.counterparty || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="金额">
        <strong :class="directionClass(bill.direction)">
          {{ formatAmount(bill.amount_cents, bill.direction) }}
        </strong>
      </el-descriptions-item>
      <el-descriptions-item label="商品说明">
        {{ bill.product_desc || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="支付方式">
        {{ bill.payment_method || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="交易状态">
        {{ bill.status || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="所属账户">
        {{ accountName }}
      </el-descriptions-item>
      <el-descriptions-item v-if="canonicalAccountName && canonicalAccountName !== accountName" label="规范账户">
        {{ canonicalAccountName }}
      </el-descriptions-item>
      <el-descriptions-item label="所属角色">
        {{ roleName }}
      </el-descriptions-item>
      <el-descriptions-item label="渠道交易单号">
        <span style="font-size:12px;word-break:break-all">{{ bill.channel_trade_no }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="备注">
        {{ bill.remark || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="业务分类">
        <el-select
          :model-value="bill.category_id"
          size="small"
          clearable
          placeholder="选择分类"
          @change="handleCategoryChange"
        >
          <el-option
            v-for="c in categories"
            :key="c.id"
            :label="c.name"
            :value="c.id"
          />
        </el-select>
      </el-descriptions-item>
    </el-descriptions>

    <div class="bill-actions">
      <el-button type="danger" size="small" @click="handleDelete">
        <el-icon><Delete /></el-icon>
        删除此账单
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const props = defineProps({
  bill: { type: Object, default: null },
})

const emit = defineEmits(['update', 'delete'])

const systemStore = useSystemStore()

const categories = computed(() => systemStore.categories)

const accountName = computed(() => {
  if (!props.bill?.account_id) return '-'
  const acc = systemStore.accounts.find(a => a.id === props.bill.account_id)
  return acc?.account_name || props.bill.account_id
})

const canonicalAccountName = computed(() => {
  if (!props.bill?.account_id) return ''
  const acc = systemStore.accounts.find(a => a.id === props.bill.account_id)
  if (!acc?.merged_into_account_id) return ''
  return acc.canonical_account_name || acc.merged_into_account_id
})

const roleName = computed(() => {
  if (!props.bill?.role_id) return '-'
  const role = systemStore.roles.find(r => r.id === props.bill.role_id)
  return role?.name || `角色#${props.bill.role_id}`
})

function tradeTypeLabel(type) {
  const map = {
    consumption: '消费',
    refund: '退款',
    transfer_out: '转出',
    transfer_in: '转入',
    repayment: '还款',
    credit_consumption: '信用消费',
    fee: '手续费',
    mirror: '镜像',
    topup: '充值',
    withdrawal: '提现',
    investment: '理财',
    other: '其他',
  }
  return map[type] || type
}

function directionClass(dir) {
  const map = { income: 'amount-income', expense: 'amount-expense', neutral: 'amount-neutral' }
  return map[dir] || ''
}

function formatAmount(cents, direction) {
  const yuan = (cents / 100).toFixed(2)
  const prefix = direction === 'income' ? '+' : direction === 'expense' ? '-' : ''
  return `${prefix}¥${yuan}`
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 19).replace('T', ' ')
}

function handleCategoryChange(categoryId) {
  emit('update', { category_id: categoryId })
  ElMessage.success('分类已更新')
}

function handleDelete() {
  ElMessageBox.confirm(
    '确定要删除此账单吗？此操作将移入回收站，可恢复。',
    '确认删除',
    { type: 'warning' }
  ).then(() => {
    emit('delete')
  }).catch(() => {})
}
</script>

<style scoped>
.bill-info {
  padding: var(--spacing-sm);
}

.bill-actions {
  margin-top: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}
</style>