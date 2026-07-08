<template>
  <div class="chart-box">
    <div class="action-bar">
      <div>
        <h4 class="chart-title">账务健康</h4>
        <div class="section-subtitle">这些状态会直接影响统计结果的可信度</div>
      </div>
    </div>

    <div class="health-grid">
      <button
        v-for="item in healthItems"
        :key="item.key"
        type="button"
        class="health-card"
        @click="$emit('item-click', item)"
      >
        <span class="health-label">{{ item.label }}</span>
        <strong class="health-value">{{ item.count }}</strong>
        <span class="health-hint">{{ item.hint }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  health: { type: Object, default: null },
})

defineEmits(['item-click'])

const healthItems = computed(() => {
  const health = props.health || {}
  return [
    { key: 'pending_assign', label: '待分配', count: health.pending_assign_count || 0, hint: '角色或账户归属待确认' },
    { key: 'uncategorized', label: '未分类', count: health.uncategorized_count || 0, hint: '支出分类会影响统计结构' },
    { key: 'orphan', label: '待溯源', count: health.orphan_count || 0, hint: '跨平台付款还未找到真实支付者' },
    { key: 'credit', label: '信用消费', count: health.credit_count || 0, hint: '可结合还款情况核对信用口径' },
    { key: 'repayment', label: '还款', count: health.repayment_count || 0, hint: '可切换隐藏内部流转查看' },
    { key: 'internal_transfer', label: '内部流转', count: health.internal_transfer_count || 0, hint: '包含转账和还款镜像' },
    { key: 'deleted', label: '回收站', count: health.deleted_count || 0, hint: '已删除账单不会进入主统计' },
  ]
})
</script>

<style scoped>
.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-sm);
}

.health-card {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-md);
  background: var(--bg-card-subtle);
  text-align: left;
  display: grid;
  gap: 6px;
}

.health-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
  font-weight: 700;
}

.health-value {
  color: var(--color-text-primary);
  font-size: 24px;
}

.health-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
