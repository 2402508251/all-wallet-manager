<template>
  <div class="data-manager">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:var(--spacing-md)">
      <template #title>
        批量操作前建议先创建手动快照。快照可回退账单与账务字段变更，但不能恢复已物理删除的记录，不等同于数据库完整备份。
      </template>
    </el-alert>

    <!-- 快照与恢复 -->
    <div class="section-title" style="margin-bottom:var(--spacing-sm)">快照与恢复</div>
    <div class="card-box manual-snapshot">
      <div class="cleanup-row">
        <div>
          <strong>手动快照</strong>
          <p class="hint">创建当前账单状态的手动快照，用于后续回退。快照仅覆盖账单与账务字段。</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <el-input
            v-model="snapshotDesc"
            placeholder="描述（可选）"
            size="small"
            style="width:200px"
          />
          <el-button type="primary" size="small" :loading="snapshotLoading" @click="handleCreateSnapshot">
            创建快照
          </el-button>
        </div>
      </div>
    </div>
    <SnapshotList @restored="refreshSnapshots" />

    <!-- 数据修正 -->
    <div class="section-title" style="margin:var(--spacing-lg) 0 var(--spacing-sm)">数据修正</div>
    <ReparsePanel @done="refreshSnapshots" />
    <RecategorizePanel @done="refreshSnapshots" />

    <!-- 清理与重置 -->
    <div class="section-title" style="margin:var(--spacing-lg) 0 var(--spacing-sm)">清理与重置</div>
    <CleanupPanel @done="refreshSnapshots" />
    <ResetApplicationPanel @done="refreshSnapshots" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import ReparsePanel from './ReparsePanel.vue'
import RecategorizePanel from './RecategorizePanel.vue'
import CleanupPanel from './CleanupPanel.vue'
import ResetApplicationPanel from './ResetApplicationPanel.vue'
import SnapshotList from './SnapshotList.vue'

const systemStore = useSystemStore()
const snapshotDesc = ref('')
const snapshotLoading = ref(false)

async function handleCreateSnapshot() {
  snapshotLoading.value = true
  try {
    const data = await systemStore.createSnapshot(snapshotDesc.value)
    ElMessage.success(`已创建手动快照，记录 ${data.bill_count} 条`)
    snapshotDesc.value = ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    snapshotLoading.value = false
  }
}

function refreshSnapshots() {
  systemStore.loadSnapshots()
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
