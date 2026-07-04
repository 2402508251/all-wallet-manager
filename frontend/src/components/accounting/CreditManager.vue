<template>
  <div class="credit-manager">
    <h4>信用账户列表</h4>
    <CreditAccountTable
      :accounts="accountingStore.creditAccounts"
      @edit="handleEditAccount"
    />

    <el-divider />

    <div class="credit-records-header">
      <h4>信用消费记录 ({{ currentMonth }})</h4>
      <el-select v-model="familyFilter" placeholder="家庭" clearable size="small" @change="loadRecords">
        <el-option v-for="f in families" :key="f.id" :label="f.name" :value="f.id" />
      </el-select>
    </div>
    <CreditRecordTable :records="accountingStore.creditRecords" />

    <el-divider />

    <h4>还款记录 ({{ currentMonth }})</h4>
    <RepayRecordTable :records="accountingStore.repayRecords" />

    <CreditAccountDialog
      ref="accountDialogRef"
      @success="accountingStore.loadCreditAccounts()"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAccountingStore } from '@/stores/accounting'
import { useSystemStore } from '@/stores/system'
import CreditAccountTable from './CreditAccountTable.vue'
import CreditRecordTable from './CreditRecordTable.vue'
import RepayRecordTable from './RepayRecordTable.vue'
import CreditAccountDialog from './CreditAccountDialog.vue'

const accountingStore = useAccountingStore()
const systemStore = useSystemStore()

const accountDialogRef = ref(null)
const familyFilter = ref(null)

const families = computed(() => systemStore.families)

const currentMonth = computed(() => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
})

onMounted(() => {
  accountingStore.loadCreditAccounts()
  loadRecords()
  systemStore.loadFamilies()
})

function loadRecords() {
  accountingStore.loadCreditRecords(currentMonth.value, familyFilter.value)
  accountingStore.loadRepayRecords(currentMonth.value, familyFilter.value)
}

function handleEditAccount(account) {
  accountDialogRef.value?.open(account)
}
</script>

<style scoped>
.credit-records-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

h4 {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-sm);
}
</style>
