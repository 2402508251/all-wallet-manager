<template>
  <div class="chart-box">
    <div class="action-bar">
      <div>
        <h4 class="chart-title">月度收支日历</h4>
        <div class="section-subtitle">按日期查看收入、支出和笔数波动</div>
      </div>
    </div>

    <div v-if="calendarItems.length" class="calendar-grid">
      <button
        v-for="item in calendarItems"
        :key="item.date"
        type="button"
        class="calendar-card"
        :style="{ background: colorFor(item.expense) }"
        @click="$emit('day-click', item)"
      >
        <span class="calendar-date">{{ dayText(item.date) }}</span>
        <strong class="calendar-expense">支出 {{ formatYuan(item.expense || 0) }}</strong>
        <span class="calendar-meta">收入 {{ formatYuan(item.income || 0) }}</span>
        <span class="calendar-meta">{{ item.bill_count || 0 }} 笔</span>
      </button>
    </div>

    <div v-else class="empty-block">
      当期暂无日历数据
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatYuan } from '@/utils/formatters'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

defineEmits(['day-click'])

const maxExpense = computed(() => {
  return props.data.reduce((max, item) => Math.max(max, item.expense || 0), 0)
})

const calendarItems = computed(() => {
  return [...props.data].sort((a, b) => String(a.date).localeCompare(String(b.date)))
})

function dayText(date) {
  return String(date || '').slice(-2)
}

function colorFor(expense) {
  const ratio = maxExpense.value ? Math.min((expense || 0) / maxExpense.value, 1) : 0
  const alpha = 0.08 + ratio * 0.24
  return `rgba(29, 78, 216, ${alpha.toFixed(3)})`
}
</script>

<style scoped>
.chart-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-sm);
}

.calendar-card {
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm);
  min-height: 104px;
  text-align: left;
  color: var(--color-text-primary);
  display: grid;
  gap: 4px;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.calendar-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-card);
}

.calendar-date {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.calendar-expense {
  font-size: var(--font-size-base);
}

.calendar-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
