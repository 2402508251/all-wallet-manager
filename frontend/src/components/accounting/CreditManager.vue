<template>
  <div class="credit-manager">
    <div class="credit-records-header">
      <div>
        <div class="section-title">信用账户列表</div>
        <div class="section-subtitle">查看当前信用账户、额度与关联状态</div>
      </div>
      <el-button type="primary" size="small" @click="handleCreateAccount">新建信用账户</el-button>
    </div>
    <CreditAccountTable
      :accounts="accountingStore.creditAccounts"
      @edit="handleEditAccount"
      @delete="handleDeleteAccount"
    />

    <el-divider />

    <div class="credit-records-header">
      <div>
        <div class="section-title">信用消费记录</div>
        <div class="section-subtitle">{{ currentMonth }}，按家庭筛选当前月信用消费与还款</div>
      </div>
      <el-select v-model="familyFilter" placeholder="家庭视角" clearable size="small" @change="loadRecords">
        <el-option v-for="f in families" :key="f.id" :label="f.name" :value="f.id" />
      </el-select>
    </div>
    <CreditRecordTable :records="accountingStore.creditRecords" />

    <el-divider />

    <div class="action-bar compact-gap">
      <div>
        <div class="section-title">还款记录</div>
        <div class="section-subtitle">用于追踪当月内部还款流转</div>
      </div>
    </div>
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

function handleCreateAccount() {
  accountDialogRef.value?.open()
}

function handleEditAccount(account) {
  accountDialogRef.value?.open(account)
}

async function handleDeleteAccount(account) {
  await accountingStore.deleteCreditAccount(account.id)
}
</script>

<style scoped>
.credit-records-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-md);
}
</style>
