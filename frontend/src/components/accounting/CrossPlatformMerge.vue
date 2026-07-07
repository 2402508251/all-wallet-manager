<template>
  <div class="cross-platform-merge">
    <h4>待溯源记录 ({{ orphanTotal }} 条)</h4>
    <p class="hint-text">第三方支付或亲属卡付款尚未找到对应真实支付者的单边账</p>
    <OrphanRecordTable
      :records="accountingStore.orphanRecords"
      :total="accountingStore.orphanTotal"
      @confirm="handleConfirm"
      @merge="handleMerge"
      @page-change="handleOrphanPage"
    />

    <el-divider />

    <h4>已溯源记录</h4>
    <MergedRecordTable
      :records="accountingStore.mergedRecords"
      @undo="handleUndo"
    />
  </div>
</template>

<script setup>
import { onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAccountingStore } from '@/stores/accounting'
import OrphanRecordTable from './OrphanRecordTable.vue'
import MergedRecordTable from './MergedRecordTable.vue'

const accountingStore = useAccountingStore()

onMounted(() => {
  accountingStore.loadOrphanRecords()
  accountingStore.loadMergedRecords()
})

const orphanTotal = computed(() => accountingStore.orphanTotal)

async function handleConfirm(bill) {
  try {
    await ElMessageBox.confirm(
      `确认将此记录(${bill.counterparty}, ¥${(bill.amount_cents / 100).toFixed(2)})作为独立消费计入统计？`,
      '确认独立计入',
      { type: 'info' }
    )
    await accountingStore.confirmOrphanIndependent(bill.id)
    ElMessage.success('已确认独立计入')
  } catch { /* 取消 */ }
}

async function handleMerge(bill) {
  try {
    await ElMessageBox.confirm(
      `尝试为此记录(${bill.counterparty}, ¥${(bill.amount_cents / 100).toFixed(2)})查找真实支付者？`,
      '尝试溯源',
      { type: 'info' }
    )
    const result = await accountingStore.tryMergeOrphan(bill.id)
    if (result.merged) {
      ElMessage.success('溯源成功')
    } else {
      ElMessage.info('未找到匹配的真实支付者')
    }
  } catch { /* 取消 */ }
}

async function handleUndo(bill) {
  try {
    await ElMessageBox.confirm('确定要撤销此次溯源吗？将恢复原始的两条记录。', '确认撤销', { type: 'warning' })
    await accountingStore.undoMerge(bill.merged_group_id)
    ElMessage.success('溯源已撤销')
  } catch { /* 取消 */ }
}

function handleOrphanPage(page) {
  accountingStore.loadOrphanRecords(page)
}
</script>

<style scoped>
h4 {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-xs);
}

.hint-text {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
}
</style>