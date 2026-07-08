<template>
  <div class="stat-cards">
    <div class="stat-card expense">
      <div class="stat-label">总支出</div>
      <div class="stat-value amount-expense">{{ formatYuan(summary.expense || 0) }}</div>
      <div class="stat-hint">日均 {{ formatYuan(summary.avg_daily_expense || 0) }}</div>
    </div>
    <div class="stat-card income">
      <div class="stat-label">总收入</div>
      <div class="stat-value amount-income">{{ formatYuan(summary.income || 0) }}</div>
      <div class="stat-hint">{{ comparisonText('income') }}</div>
    </div>
    <div class="stat-card neutral">
      <div class="stat-label">结余</div>
      <div class="stat-value" :class="netClass">{{ formatYuan(summary.net || 0) }}</div>
      <div class="stat-hint">{{ comparisonText('net') }}</div>
    </div>
    <div class="stat-card credit">
      <div class="stat-label">信用消费 / 还款</div>
      <div class="stat-value amount-expense">{{ formatYuan(summary.credit || 0) }}</div>
      <div class="stat-hint">还款 {{ formatYuan(summary.repayment || 0) }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">退款</div>
      <div class="stat-value amount-income">{{ formatYuan(summary.refund || 0) }}</div>
      <div class="stat-hint">共 {{ counts.refund_count || 0 }} 笔</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">账单笔数</div>
      <div class="stat-value">{{ counts.bill_count || 0 }}</div>
      <div class="stat-hint">支出 {{ counts.expense_count || 0 }} / 收入 {{ counts.income_count || 0 }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  overview: { type: Object, default: null },
})

const summary = computed(() => props.overview?.summary || {})
const comparison = computed(() => props.overview?.comparison || {})
const counts = computed(() => props.overview?.counts || {})
const netClass = computed(() => (summary.value.net || 0) >= 0 ? 'amount-income' : 'amount-expense')

function comparisonText(field) {
  if (field === 'net') {
    const current = summary.value?.net || 0
    const previous = comparison.value?.net_previous
    if (previous === null || previous === undefined) return '无可比历史数据'
    const delta = current - previous
    if (delta === 0) return '与上期持平'
    return delta > 0 ? `较上期增加 ${formatYuan(delta)}` : `较上期减少 ${formatYuan(Math.abs(delta))}`
  }

  const ratio = comparison.value?.[`${field}_change_ratio`]
  if (ratio === null || ratio === undefined) return '无可比历史数据'
  const percent = `${Math.abs(ratio * 100).toFixed(1)}%`
  if (ratio === 0) return '与上期持平'
  return ratio > 0 ? `较上期增加 ${percent}` : `较上期下降 ${percent}`
}
</script>

<style scoped>
.stat-card {
  min-height: 132px;
  padding: var(--spacing-lg);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.stat-card.expense {
  background: linear-gradient(180deg, #ffffff, rgba(245, 108, 108, 0.08));
}

.stat-card.income {
  background: linear-gradient(180deg, #ffffff, rgba(103, 194, 58, 0.08));
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
  color: var(--color-text-primary);
}

.stat-hint {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>
