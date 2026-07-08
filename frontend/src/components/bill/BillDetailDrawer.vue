<template>
  <el-drawer
    v-model="visible"
    title="账单详情"
    :size="640"
    direction="rtl"
    @close="handleClose"
  >
    <div v-if="bill" class="detail-summary">
      <div class="detail-summary-meta">
        <span class="detail-summary-time">{{ summaryTime }}</span>
        <strong :class="summaryAmountClass">{{ summaryAmount }}</strong>
      </div>
      <div class="detail-summary-desc">{{ bill.product_desc || bill.counterparty || '账单详情' }}</div>
    </div>

    <el-tabs v-model="activeTab" v-loading="loading">
      <el-tab-pane label="基础信息" name="basic">
        <BillBasicInfo
          :bill="bill"
          @update="handleUpdate"
          @delete="handleDelete"
        />
      </el-tab-pane>
      <el-tab-pane label="源账单" name="source">
        <BillSourceInfo :source-bill="sourceBill" />
      </el-tab-pane>
      <el-tab-pane label="账务状态" name="accounting">
        <BillAccountingInfo :bill="bill" />
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useBillStore } from '@/stores/bill'
import { useSystemStore } from '@/stores/system'
import BillBasicInfo from './BillBasicInfo.vue'
import BillSourceInfo from './BillSourceInfo.vue'
import BillAccountingInfo from './BillAccountingInfo.vue'
import { directionClass, formatDateTime, formatSignedYuan } from '@/utils/formatters'

const props = defineProps({
  billId: { type: Number, default: null },
})

const emit = defineEmits(['close', 'update', 'delete'])

const billStore = useBillStore()
const systemStore = useSystemStore()

const visible = ref(false)
const activeTab = ref('basic')
const bill = ref(null)
const sourceBill = ref(null)
const loading = ref(false)
const summaryTime = computed(() => formatDateTime(bill.value?.trade_time))
const summaryAmount = computed(() => formatSignedYuan(bill.value?.amount_cents || 0, bill.value?.direction))
const summaryAmountClass = computed(() => directionClass(bill.value?.direction))

watch(() => props.billId, async (id) => {
  if (id) {
    visible.value = true
    loading.value = true
    try {
      await Promise.all([
        systemStore.loadFamilies(),
        systemStore.loadRoles(null),
        systemStore.loadAccounts(null),
        systemStore.loadCategories(),
        billStore.getBillDetail(id),
      ]).then(results => {
        bill.value = results[4]
        sourceBill.value = results[4]?.source_bill || null
      })
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })

function handleClose() {
  visible.value = false
  activeTab.value = 'basic'
  emit('close')
}

async function handleUpdate(fields) {
  if (props.billId) {
    await billStore.updateBill(props.billId, fields)
    emit('update', fields)
    // 刷新详情
    const data = await billStore.getBillDetail(props.billId)
    bill.value = data
  }
}

async function handleDelete() {
  if (props.billId) {
    await billStore.deleteBill(props.billId)
    visible.value = false
    emit('delete')
  }
}
</script>

<style scoped>
.detail-summary {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-md);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  background: var(--bg-card-subtle);
}

.detail-summary-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
}

.detail-summary-time {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.detail-summary-desc {
  margin-top: var(--spacing-xs);
  color: var(--color-text-primary);
  font-weight: 700;
}
</style>
