<template>
  <div class="page-container">
    <h2 class="page-title">账单采集</h2>

    <!-- 拖拽上传区域 -->
    <FileUploader @upload-success="onUploadSuccess" />

    <!-- 邮箱拉取区 -->
    <div class="card-box email-section">
      <div class="email-header">
        <span>📧 通过邮箱拉取账单</span>
        <div class="email-actions">
          <el-button size="small" @click="openEmailConfig">
            <el-icon><Setting /></el-icon>
            邮箱配置
          </el-button>
          <el-button
            v-if="emailConfigs.length > 0"
            type="primary"
            size="small"
            @click="handleSyncBills"
          >
            <el-icon><Refresh /></el-icon>
            同步账单
          </el-button>
        </div>
      </div>
    </div>

    <!-- 任务进度 -->
    <ProgressPanel />

    <!-- 采集结果列表 -->
    <CollectionTable
      :collections="collectionStore.collections"
      :total="collectionStore.total"
      :loading="collectionStore.loading"
      @parse="handleParse"
      @set-channel="handleSetChannel"
      @set-password="handleSetPassword"
      @view-result="handleViewResult"
      @delete-records="handleDeleteRecords"
      @delete-bills="handleDeleteBills"
    />

    <!-- 子组件弹窗 -->
    <EmailConfig ref="emailConfigRef" @sync-bills="handleSyncBills" />
    <ZipPasswordDialog ref="zipPwdRef" @success="refreshList" />
    <ParseResultDialog ref="parseResultRef" />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, Refresh } from '@element-plus/icons-vue'
import { useCollectionStore } from '@/stores/collection'
import { onTaskProgress } from '@/utils/bridge'

import FileUploader from '@/components/collection/FileUploader.vue'
import EmailConfig from '@/components/collection/EmailConfig.vue'
import ProgressPanel from '@/components/collection/ProgressPanel.vue'
import CollectionTable from '@/components/collection/CollectionTable.vue'
import ZipPasswordDialog from '@/components/collection/ZipPasswordDialog.vue'
import ParseResultDialog from '@/components/collection/ParseResultDialog.vue'

const collectionStore = useCollectionStore()

const emailConfigRef = ref(null)
const zipPwdRef = ref(null)
const parseResultRef = ref(null)

const emailConfigs = computed(() => collectionStore.emailConfigs)

onMounted(() => {
  collectionStore.loadCollections()
  collectionStore.loadEmailConfigs()
})

function onUploadSuccess() {
  collectionStore.loadCollections()
}

function refreshList() {
  collectionStore.loadCollections()
}

function openEmailConfig() {
  emailConfigRef.value?.open()
}

async function handleSyncBills() {
  if (emailConfigs.value.length === 0) {
    ElMessage.warning('请先配置邮箱')
    return
  }

  try {
    await ElMessageBox.confirm(
      '将连接邮箱拉取账单附件，此操作可能需要一些时间。确认继续？',
      '确认同步',
      { type: 'info' }
    )
  } catch {
    return
  }

  for (const config of emailConfigs.value) {
    try {
      const data = await collectionStore.fetchEmailBills(config.id)
      if (data?.task_id) {
        collectionStore.startTaskListeners(data.task_id)
      }
    } catch (e) {
      ElMessage.error(`${config.email_addr}: ${e.message}`)
    }
  }
}

async function handleParse(row) {
  try {
    const data = await collectionStore.parseCollection(row.id)
    if (data) {
      parseResultRef.value?.open(data)
    }
  } catch (e) {
    ElMessage.error(e.message || '解析失败')
  }
}

async function handleSetChannel(row, channel) {
  try {
    await collectionStore.setChannelManual(row.id, channel)
    ElMessage.success(`已设置渠道为 ${channel}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function handleSetPassword(row) {
  zipPwdRef.value?.open(row)
}

function handleViewResult(row) {
  if (row.parse_result) {
    try {
      const result = typeof row.parse_result === 'string'
        ? JSON.parse(row.parse_result)
        : row.parse_result
      parseResultRef.value?.open(result)
    } catch {
      ElMessage.warning('解析结果数据异常')
    }
  }
}

async function handleDeleteRecords(recordIds) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${recordIds.length} 条采集记录？已解析的记录需先删除关联账单。`,
      '删除采集记录',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    const data = await collectionStore.deleteCollectionRecords(recordIds)
    if (data.blocked?.length > 0) {
      ElMessage.warning(`${data.deleted_count} 条已删除，${data.blocked.length} 条因关联账单未删除被阻止`)
    } else {
      ElMessage.success(`已删除 ${data.deleted_count} 条采集记录`)
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function handleDeleteBills(recordIds) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${recordIds.length} 条采集记录关联的账单数据？采集记录将保留。`,
      '删除关联账单',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    const data = await collectionStore.deleteBillsByCollections(recordIds)
    ElMessage.success(`已删除 ${data.deleted_count} 条账单`)
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
</script>

<style scoped>
.email-section {
  margin-bottom: var(--spacing-md);
}

.email-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.email-actions {
  display: flex;
  gap: var(--spacing-sm);
}
</style>