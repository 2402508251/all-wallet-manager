<template>
  <el-dialog
    v-model="visible"
    title="解析结果"
    width="450px"
    :close-on-click-modal="false"
  >
    <div v-if="result" class="parse-result">
      <div class="result-item">
        <el-icon :size="20" color="#67c23a"><SuccessFilled /></el-icon>
        <span class="result-label">解析完成</span>
      </div>

      <el-divider />

      <div class="result-stats">
        <div class="stat-row">
          <span>总记录数：</span>
          <strong>{{ result.total || 0 }}</strong>
        </div>
        <div class="stat-row">
          <span>成功导入：</span>
          <strong class="text-success">{{ result.success || 0 }} 条</strong>
        </div>
        <div class="stat-row">
          <span>重复跳过：</span>
          <strong class="text-warning">{{ result.duplicate || 0 }} 条</strong>
        </div>
        <div class="stat-row" v-if="result.accounts_created !== undefined">
          <span>新建账户：</span>
          <strong>{{ result.accounts_created || 0 }} 个</strong>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="visible = false">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { SuccessFilled } from '@element-plus/icons-vue'

const visible = ref(false)
const result = ref(null)

function open(data) {
  result.value = data
  visible.value = true
}

defineExpose({ open })
</script>

<style scoped>
.parse-result {
  text-align: center;
}

.result-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.result-label {
  font-size: var(--font-size-large);
  font-weight: 600;
  color: var(--color-success);
}

.result-stats {
  text-align: left;
  padding: 0 var(--spacing-md);
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-xs) 0;
  font-size: var(--font-size-base);
}

.stat-row span {
  color: var(--color-text-secondary);
}

.text-success {
  color: var(--color-success);
}

.text-warning {
  color: var(--color-warning);
}
</style>
