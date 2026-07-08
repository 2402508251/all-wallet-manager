<template>
  <div v-if="bill" class="bill-info">
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="交易时间">
        {{ formatTime(bill.trade_time) }}
      </el-descriptions-item>
      <el-descriptions-item label="交易类型">
        <el-tag size="small" :type="tradeTypeTag(bill.trade_type)">{{ tradeTypeLabel(bill.trade_type) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="渠道">
        <el-tag size="small" :type="channelTag(bill.channel)">
          {{ channelLabel(bill.channel) }}
        </el-tag>
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
        <span class="long-text">{{ bill.channel_trade_no }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="备注">
        <div class="remark-editor">
          <el-input
            v-model="remarkDraft"
            type="textarea"
            :rows="3"
            resize="vertical"
            maxlength="300"
            show-word-limit
            placeholder="填写备注信息"
          />
          <div class="remark-actions">
            <el-button size="small" @click="resetRemark" :disabled="!remarkChanged">恢复原值</el-button>
            <el-button type="primary" size="small" @click="saveRemark" :disabled="!remarkChanged">保存备注</el-button>
          </div>
        </div>
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
import { computed, ref, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'
import {
  channelLabel,
  channelTag,
  directionClass,
  formatDateTime,
  formatSignedYuan,
  tradeTypeLabel,
  tradeTypeTag,
} from '@/utils/formatters'

const props = defineProps({
  bill: { type: Object, default: null },
})

const emit = defineEmits(['update', 'delete'])

const systemStore = useSystemStore()
const remarkDraft = ref('')

const categories = computed(() => systemStore.categories)
const normalizedBillRemark = computed(() => String(props.bill?.remark || ''))
const remarkChanged = computed(() => remarkDraft.value !== normalizedBillRemark.value)

watch(() => props.bill, (bill) => {
  remarkDraft.value = String(bill?.remark || '')
}, { immediate: true })

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

function formatAmount(cents, direction) {
  return formatSignedYuan(cents, direction)
}

function formatTime(timeStr) {
  return formatDateTime(timeStr)
}

function handleCategoryChange(categoryId) {
  emit('update', { category_id: categoryId })
  ElMessage.success('分类已更新')
}

function resetRemark() {
  remarkDraft.value = normalizedBillRemark.value
}

function saveRemark() {
  if (!remarkChanged.value) return
  emit('update', { remark: remarkDraft.value.trim() })
  ElMessage.success('备注已更新')
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

.remark-editor {
  display: grid;
  gap: var(--spacing-sm);
}

.remark-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

.long-text {
  font-size: 12px;
  word-break: break-all;
}
</style>
