<template>
  <el-dialog
    v-model="visible"
    title="ZIP 解压密码"
    width="400px"
    :close-on-click-modal="false"
  >
    <el-form @submit.prevent="handleConfirm">
      <el-form-item label="密码">
        <el-input
          v-model="password"
          type="password"
          show-password
          placeholder="请输入 ZIP 解压密码"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleConfirm">
        确认解压
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCollectionStore } from '@/stores/collection'

const emit = defineEmits(['success'])

const collectionStore = useCollectionStore()

const visible = ref(false)
const password = ref('')
const recordId = ref(null)
const submitting = ref(false)

function open(record) {
  recordId.value = record.id
  password.value = ''
  visible.value = true
}

async function handleConfirm() {
  if (!password.value) {
    ElMessage.warning('请输入解压密码')
    return
  }

  submitting.value = true
  try {
    const data = await collectionStore.setZipPassword(recordId.value, password.value)
    const extractedCount = data?.extracted_count || 0
    const duplicateSkipped = data?.duplicate_skipped || 0
    if (duplicateSkipped > 0) {
      ElMessage.success(`解压成功，新增 ${extractedCount} 条记录，跳过 ${duplicateSkipped} 条重复记录`)
    } else {
      ElMessage.success(`解压成功，新增 ${extractedCount} 条记录`)
    }
    visible.value = false
    emit('success')
  } catch (e) {
    ElMessage.error(e.message || '解压失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>
