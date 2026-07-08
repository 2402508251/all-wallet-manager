<template>
  <div class="page-container">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Accounting</div>
        <h2 class="page-title">账务处理工作台</h2>
        <p class="page-subtitle">处理信用消费、跨平台真实支付者溯源和账户间转账配对，保持统计口径清晰。</p>
      </div>
    </section>

    <div class="accounting-shell">
      <div class="accounting-summary">
        <button
          v-for="item in tabItems"
          :key="item.name"
          type="button"
          class="accounting-tab"
          :class="{ 'is-active': activeTab === item.name }"
          @click="onTabChange(item.name)"
        >
          <strong>{{ item.label }}</strong>
          <span>{{ item.desc }}</span>
        </button>
      </div>

      <div class="card-box accounting-panel">
      <el-tabs v-model="activeTab" class="hidden-tabs" @tab-change="onTabChange">
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
const tabItems = [
  { name: 'credit', label: '信用消费管理', desc: '信用账户、消费与还款记录' },
  { name: 'merge', label: '真实支付者溯源', desc: '处理跨平台重复流水与孤立记录' },
  { name: 'transfer', label: '转账配对', desc: '确认账户间转入转出关系' },
]

function onTabChange(name) {
  activeTab.value = name
  accountingStore.activeTab = name
}
</script>

<style scoped>
.accounting-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: var(--spacing-md);
  align-items: start;
}

.accounting-summary {
  display: grid;
  gap: var(--spacing-sm);
}

.accounting-tab {
  display: grid;
  gap: var(--spacing-xs);
  width: 100%;
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  background: var(--bg-card);
  color: var(--color-text-regular);
  cursor: pointer;
  text-align: left;
  box-shadow: var(--shadow-card);
}

.accounting-tab strong {
  color: var(--color-text-primary);
}

.accounting-tab span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.accounting-tab.is-active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.accounting-panel {
  min-width: 0;
}

.hidden-tabs :deep(.el-tabs__header) {
  display: none;
}

@media (max-width: 1200px) {
  .accounting-shell {
    grid-template-columns: 1fr;
  }

  .accounting-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
