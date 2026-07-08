<template>
  <div class="card-box reset-panel">
    <div class="reset-copy">
      <strong>重置应用</strong>
      <p class="hint">删除并重建数据库，恢复为全新安装状态。账单、账户、角色、邮箱配置、快照和自定义分类都会被清空。</p>
      <el-checkbox v-model="createBackup">重置前创建数据库备份</el-checkbox>
    </div>
    <el-button type="danger" :loading="resetting" @click="handleReset">重置应用</el-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const emit = defineEmits(['done'])

const systemStore = useSystemStore()
const createBackup = ref(true)
const resetting = ref(false)

async function handleReset() {
  try {
    const { value } = await ElMessageBox.prompt(
      '此操作会删除并重建整个应用数据库。请输入 RESET 确认继续。',
      '重置应用',
      {
        type: 'error',
        confirmButtonText: '确认重置',
        cancelButtonText: '取消',
        inputPattern: /^RESET$/,
        inputErrorMessage: '请输入 RESET',
      }
    )

    resetting.value = true
    const result = await systemStore.resetApplication({
      confirm_text: value,
      backup: createBackup.value,
    })
    await Promise.all([
      systemStore.loadFamilies(),
      systemStore.loadRoles(),
      systemStore.loadAccounts(),
      systemStore.loadCategories(),
      systemStore.loadSnapshots(),
    ])
    ElMessage.success(result.backup_path ? `应用已重置，备份：${result.backup_path}` : '应用已重置')
    emit('done')
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    resetting.value = false
  }
}
</script>

<style scoped>
.reset-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  border-color: var(--color-danger-light-7);
}

.reset-copy {
  display: grid;
  gap: var(--spacing-xs);
}

.reset-copy strong {
  font-size: var(--font-size-base);
}

.hint {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin: 0;
}
</style>
