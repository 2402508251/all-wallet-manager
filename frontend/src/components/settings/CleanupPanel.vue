<template>
  <div class="card-box">
    <el-alert type="error" :closable="false" show-icon style="margin-bottom:16px">
      <template #title>
        ⚠️ 数据清理操作不可逆，请在操作前确认已创建快照备份
      </template>
    </el-alert>

    <div class="cleanup-actions">
      <div class="cleanup-row">
        <div>
          <strong>一键清除所有账单</strong>
          <p class="hint">删除所有统一账单、源账单、导入批次数据，采集记录重置为待解析状态</p>
        </div>
        <el-button type="danger" @click="handleClearAll">一键清除</el-button>
      </div>

      <el-divider />

      <div class="cleanup-row">
        <div>
          <strong>清理源账单数据</strong>
          <p class="hint">删除已逻辑删除账单对应的源数据，释放存储空间</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <el-date-picker
            v-model="beforeDate"
            type="date"
            placeholder="选择截止日期"
            value-format="YYYY-MM-DD"
            size="small"
          />
          <el-button size="small" @click="handleCleanupSource">清理</el-button>
        </div>
      </div>

      <el-divider />

      <div class="cleanup-row">
        <div>
          <strong>清理旧快照</strong>
          <p class="hint">保留最近 N 条快照，删除更早的快照以释放存储空间</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <el-input-number v-model="keepCount" :min="1" :max="200" size="small" style="width:100px" />
          <span style="color:#909399;font-size:12px">条</span>
          <el-button size="small" @click="handleCleanupSnapshots">清理</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const emit = defineEmits(['done'])

const systemStore = useSystemStore()
const beforeDate = ref(null)
const keepCount = ref(50)

async function handleClearAll() {
  try {
    await ElMessageBox.confirm(
      '确定要清除所有账单数据吗？\n此操作将删除：\n- 所有统一账单\n- 所有源账单\n- 所有导入批次\n\n采集记录将重置为待解析状态。此操作不可恢复！',
      '⚠️ 危险操作',
      { type: 'error', confirmButtonText: '确认清除', cancelButtonText: '取消' }
    )
    await systemStore.clearAllBills()
    ElMessage.success('所有账单数据已清除')
    emit('done')
  } catch { /* 取消 */ }
}

async function handleCleanupSource() {
  const date = beforeDate.value
  if (!date) {
    ElMessage.warning('请选择截止日期')
    return
  }
  try {
    const result = await systemStore.cleanupSourceBills(date)
    ElMessage.success(`已清理 ${result.deleted_count} 条源账单数据`)
    emit('done')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleCleanupSnapshots() {
  try {
    const result = await systemStore.cleanupSnapshots(keepCount.value)
    ElMessage.success(`已清理 ${result.deleted_count} 条旧快照`)
    emit('done')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.cleanup-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
}

.cleanup-row strong {
  font-size: var(--font-size-base);
}

.hint {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin-top: 2px;
}
</style>
