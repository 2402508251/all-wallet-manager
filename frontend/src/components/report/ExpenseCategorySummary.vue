<template>
  <section class="surface-box expense-category-section">
    <div class="action-bar section-header">
      <div>
        <div class="section-title">支出分类洞察</div>
        <div class="section-subtitle">先看分类集中度、头部分类和未分类情况，再下钻到具体账单。</div>
      </div>
      <el-button
        v-if="(summary?.uncategorized_count || 0) > 0"
        type="danger"
        plain
        size="small"
        @click="$emit('uncategorized-click')"
      >
        查看未分类
      </el-button>
    </div>

    <div class="summary-grid">
      <div class="insight-card">
        <span class="insight-label">支出分类数</span>
        <strong class="insight-value">{{ summary?.category_count || 0 }}</strong>
        <span class="insight-hint">已形成分类结构的支出类别</span>
      </div>
      <div class="insight-card">
        <span class="insight-label">最大分类支出</span>
        <strong class="insight-value">{{ summary?.top_category_label || '暂无' }}</strong>
        <span class="insight-hint">{{ formatYuan(summary?.top_category_amount || 0) }}</span>
      </div>
      <div class="insight-card">
        <span class="insight-label">前三分类占比</span>
        <strong class="insight-value">{{ percent(summary?.top3_ratio) }}</strong>
        <span class="insight-hint">越高说明支出更集中</span>
      </div>
      <button type="button" class="insight-card warning-card" @click="$emit('uncategorized-click')">
        <span class="insight-label">未分类支出</span>
        <strong class="insight-value">{{ formatYuan(summary?.uncategorized_amount || 0) }}</strong>
        <span class="insight-hint">
          {{ summary?.uncategorized_count || 0 }} 笔 / {{ percent(summary?.uncategorized_ratio) }}
        </span>
      </button>
    </div>
  </section>
</template>

<script setup>
import { formatYuan } from '@/utils/formatters'

defineProps({
  summary: { type: Object, default: null },
})

defineEmits(['uncategorized-click'])

function percent(value) {
  return `${(((value || 0) * 100)).toFixed(1)}%`
}
</script>

<style scoped>
.expense-category-section {
  padding: var(--spacing-md);
}

.section-header {
  margin-bottom: var(--spacing-md);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--spacing-md);
}

.insight-card {
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  padding: var(--spacing-md);
  display: grid;
  gap: 6px;
  min-height: 122px;
  text-align: left;
}

.warning-card {
  cursor: pointer;
  background: linear-gradient(180deg, #ffffff, rgba(245, 108, 108, 0.08));
}

.insight-label {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  font-weight: 700;
}

.insight-value {
  font-size: 24px;
  line-height: 1.2;
  color: var(--color-text-primary);
}

.insight-hint {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}

@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
