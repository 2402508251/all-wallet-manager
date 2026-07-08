<template>
  <div class="transfer-pairer">
    <div class="action-bar">
      <div>
        <div class="section-title">已自动配对</div>
        <div class="section-subtitle">强匹配 {{ strongPairs.length }} 条，基于备注或单号线索自动生成转账配对</div>
      </div>
    </div>
    <StrongPairTable :pairs="strongPairs" />

    <el-divider />

    <div class="action-bar">
      <div>
        <div class="section-title">待确认配对</div>
        <div class="section-subtitle">从未配对的转出记录中提取弱匹配候选，需要手动确认</div>
      </div>
    </div>
    <WeakPairTable
      :candidates="accountingStore.weakCandidates"
      @confirm="handleConfirmPair"
      @reject="handleRejectPair"
    />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountingStore } from '@/stores/accounting'
import StrongPairTable from './StrongPairTable.vue'
import WeakPairTable from './WeakPairTable.vue'

const accountingStore = useAccountingStore()
const strongPairs = computed(() => accountingStore.strongPairs)

onMounted(() => {
  accountingStore.loadStrongPairs()
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

async function handleRejectPair({ outId, inId }) {
  try {
    await accountingStore.rejectTransferPair(outId, inId)
    ElMessage.success('已拒绝配对')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>
