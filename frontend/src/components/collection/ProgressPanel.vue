<template>
  <div v-if="activeTask" class="card-box progress-panel">
    <div class="progress-header">
      <el-icon class="is-loading" :size="20"><Loading /></el-icon>
      <span class="progress-message">{{ activeTask.message || '处理中...' }}</span>
    </div>
    <el-progress
      :percentage="activeTask.percent || 0"
      :status="activeTask.percent === 100 ? 'success' : ''"
      :stroke-width="8"
    />
    <div v-if="activeTask.step" class="progress-step">
      {{ activeTask.step }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useCollectionStore } from '@/stores/collection'

const collectionStore = useCollectionStore()

const activeTask = computed(() => {
  const tasks = Object.values(collectionStore.activeTasks)
  return tasks.length > 0 ? tasks[0] : null
})
</script>

<style scoped>
.progress-panel {
  margin-bottom: var(--spacing-md);
}

.progress-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.progress-message {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.progress-step {
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>
