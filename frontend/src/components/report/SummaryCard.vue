<template>
  <div class="stat-cards">
    <div class="stat-card">
      <div class="stat-label">总支出</div>
      <div class="stat-value amount-expense">
        {{ formatYuan(summary?.expense || 0) }}
      </div>
      <div class="stat-hint">不含信用消费</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">总收入</div>
      <div class="stat-value amount-income">
        {{ formatYuan(summary?.income || 0) }}
      </div>
      <div class="stat-hint">已排除逻辑删除账单</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">信用消费</div>
      <div class="stat-value amount-expense">
        {{ formatYuan(summary?.credit || 0) }}
      </div>
      <div class="stat-hint">花呗/白条/分付</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">还款金额</div>
      <div class="stat-value amount-expense">
        {{ formatYuan(summary?.repayment || 0) }}
      </div>
      <div class="stat-hint">用于识别内部流转</div>
    </div>
  </div>
</template>

<script setup>
import { formatYuan } from '@/utils/formatters'

defineProps({
  summary: { type: Object, default: null },
})
</script>

<style scoped>
.stat-card {
  min-height: 128px;
  padding: var(--spacing-lg);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.stat-label {
  font-size: var(--font-size-small);
  font-weight: 700;
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: var(--spacing-xs);
}

.stat-hint {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>
