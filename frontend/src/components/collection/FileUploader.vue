<template>
  <div class="card-box">
    <div
      class="upload-area"
      :class="{ 'is-uploading': uploading }"
      @click="handleSelectFiles"
    >
      <template v-if="uploading">
        <el-icon class="upload-icon is-spin"><Loading /></el-icon>
        <div class="upload-text">
          <p class="upload-title">正在添加采集记录...</p>
        </div>
      </template>
      <template v-else>
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">
          <p class="upload-title">点击选择微信/支付宝/建行账单文件</p>
          <p class="upload-types">支持 .xlsx .csv .xls .zip .pdf（可多选）</p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Loading } from '@element-plus/icons-vue'
import { useCollectionStore } from '@/stores/collection'
import { call } from '@/utils/bridge'

const emit = defineEmits(['upload-success'])

const collectionStore = useCollectionStore()
const uploading = ref(false)

async function handleSelectFiles() {
  if (uploading.value) return

  let paths
  try {
    const data = await call('select_files', {})
    paths = data.paths || []
  } catch (e) {
    ElMessage.error(e.message || '文件选择失败')
    return
  }

  if (paths.length === 0) return

  const files = paths.map(p => ({
    name: p.split(/[\\/]/).pop(),
    path: p,
  }))

  uploading.value = true
  try {
    const result = await collectionStore.uploadFiles(files)
    const count = result?.count || files.length
    ElMessage.success(`成功添加 ${count} 条采集记录`)
    emit('upload-success')
  } catch (e) {
    ElMessage.error(e.message || '添加采集记录失败')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-area {
  width: 100%;
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl) var(--spacing-md);
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  user-select: none;
}

.upload-area:hover {
  border-color: var(--color-primary);
  background: rgba(64, 158, 255, 0.03);
}

.upload-area.is-uploading {
  cursor: wait;
  border-color: var(--color-primary);
  background: rgba(64, 158, 255, 0.05);
}

.upload-icon {
  font-size: 48px;
  color: var(--color-primary-light);
  margin-bottom: var(--spacing-sm);
}

.upload-icon.is-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.upload-title {
  font-size: var(--font-size-large);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.upload-types {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>