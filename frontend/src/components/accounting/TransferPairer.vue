<template>
  <div class="transfer-pairer">
    <h4>已自动配对 (强匹配) ({{ strongPairs.length }} 条)</h4>
    <StrongPairTable :pairs="strongPairs" />

    <el-divider />

    <h4>待确认配对 (弱匹配)</h4>
    <WeakPairTable
      :candidates="accountingStore.weakCandidates"
      @confirm="handleConfirmPair"
      @reject="handleRejectPair"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountingStore } from '@/stores/accounting'
import StrongPairTable from './StrongPairTable.vue'
import WeakPairTable from './WeakPairTable.vue'

const accountingStore = useAccountingStore()

const strongPairs = ref([])

onMounted(() => {
  accountingStore.loadStrongPairs().then(() => {
    strongPairs.value = accountingStore.strongPairs
  })
  accountingStore.loadWeakCandidates()
})

async function handleConfirmPair({ outId, inId }) {
  try {
    const data = await accountingStore.confirmTransferPair(outId, inId)
    ElMessage.success(`配对成功: ${data.transfer_link_id}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleRejectPair(candidateId) {
  try {
    await accountingStore.rejectTransferPair(candidateId)
    ElMessage.success('已拒绝配对')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
h4 {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
}
</style>
