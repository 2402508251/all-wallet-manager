<template>
  <div class="stat-cards">
    <div class="card-box stat-card">
      <div class="stat-label">总支出</div>
      <div class="stat-value amount-expense">
        ¥{{ formatYuan(summary?.expense || 0) }}
      </div>
      <div class="stat-hint">不含信用消费</div>
    </div>
    <div class="card-box stat-card">
      <div class="stat-label">总收入</div>
      <div class="stat-value amount-income">
        ¥{{ formatYuan(summary?.income || 0) }}
      </div>
    </div>
    <div class="card-box stat-card">
      <div class="stat-label">信用消费</div>
      <div class="stat-value amount-expense">
        ¥{{ formatYuan(summary?.credit || 0) }}
      </div>
      <div class="stat-hint">花呗/白条/分付</div>
    </div>
    <div class="card-box stat-card">
      <div class="stat-label">还款金额</div>
      <div class="stat-value amount-expense">
        ¥{{ formatYuan(summary?.repayment || 0) }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  summary: { type: Object, default: null },
})

function formatYuan(cents) {
  return (cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.stat-card {
  text-align: center;
  padding: var(--spacing-lg);
}

.stat-label {
  font-size: var(--font-size-base);
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
  color: var(--color-text-placeholder);
}
</style>
