<template>
  <div>
    <div class="action-bar">
      <span>快照记录 (最近 {{ limit }} 条)</span>
      <el-button size="small" @click="loadSnapshots">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-table :data="systemStore.snapshots" style="width: 100%" size="small" empty-text="暂无快照">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ snapshotTypeLabel(row.snapshot_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      <el-table-column prop="bill_count" label="记录数" width="80" align="right" />
      <el-table-column label="时间" width="160">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="showDetails(row)">明细</el-button>
          <el-button link type="warning" size="small" @click="handleRestore(row)">回退</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 明细弹窗 -->
    <el-dialog v-model="detailVisible" title="快照相异明细" width="700px">
      <el-table :data="details" style="width: 100%" size="small" max-height="400" empty-text="无变更明细">
        <el-table-column label="账单ID" width="80">
          <template #default="{ row }">#{{ row.bill_id }}</template>
        </el-table-column>
        <el-table-column prop="table_name" label="来源表" width="130" />
        <el-table-column prop="field_name" label="字段名" width="130" />
        <el-table-column label="旧值" min-width="150">
          <template #default="{ row }">
            <span class="old-value">{{ row.old_value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="新值" min-width="150">
          <template #default="{ row }">
            <span class="new-value">{{ row.new_value }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const emit = defineEmits(['restored'])

const systemStore = useSystemStore()
const limit = ref(20)
const detailVisible = ref(false)
const details = ref([])

onMounted(() => {
  loadSnapshots()
})

async function loadSnapshots() {
  await systemStore.loadSnapshots(limit.value)
}

async function showDetails(row) {
  try {
    details.value = await systemStore.getSnapshotDetails(row.id)
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleRestore(row) {
  try {
    await ElMessageBox.confirm(
      '确定要回退到此快照状态吗？系统将恢复快照中已记录的账单与账务字段变更。\n\n注意：若记录在快照创建后被物理删除，当前快照无法将其重建恢复。',
      '确认回退',
      { type: 'warning' }
    )
    await systemStore.restoreSnapshot(row.id)
    ElMessage.success('快照已回退')
    emit('restored')
    loadSnapshots()
  } catch { /* 取消 */ }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定要删除此快照吗？', '确认删除', { type: 'warning' })
    await systemStore.deleteSnapshot(row.id)
    ElMessage.success('快照已删除')
    loadSnapshots()
  } catch { /* 取消 */ }
}

function snapshotTypeLabel(type) {
  const map = {
    manual: '手动快照',
    reparse: '重新解析',
    recategorize: '重新分类',
    batch_import: '批量导入',
    account_role_change: '帐户角色变更',
    batch_account_role_change: '批量帐户角色变更',
    batch_reassign: '批量重分配',
  }
  return map[type] || type
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 16).replace('T', ' ')
}
</script>

<style scoped>
.old-value { color: var(--color-danger); }
.new-value { color: var(--color-success); }
</style>
