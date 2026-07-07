<template>
  <div class="page-container">
    <h2 class="page-title">账务处理</h2>

    <div class="card-box">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="信用消费管理" name="credit">
          <CreditManager />
        </el-tab-pane>
        <el-tab-pane label="真实支付者溯源" name="merge">
          <CrossPlatformMerge />
        </el-tab-pane>
        <el-tab-pane label="转账配对" name="transfer">
          <TransferPairer />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAccountingStore } from '@/stores/accounting'
import CreditManager from '@/components/accounting/CreditManager.vue'
import CrossPlatformMerge from '@/components/accounting/CrossPlatformMerge.vue'
import TransferPairer from '@/components/accounting/TransferPairer.vue'

const accountingStore = useAccountingStore()
const activeTab = ref(accountingStore.activeTab)

function onTabChange(name) {
  accountingStore.activeTab = name
}
</script>
