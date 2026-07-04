<template>
  <el-dialog
    v-model="visible"
    title="邮箱配置管理"
    width="650px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 邮箱列表 -->
    <el-table :data="emailConfigs" style="width: 100%" size="default" max-height="300">
      <el-table-column prop="email_addr" label="邮箱地址" min-width="180" />
      <el-table-column prop="imap_server" label="IMAP服务器" width="150" />
      <el-table-column prop="imap_port" label="端口" width="70" />
      <el-table-column label="上次拉取" width="130">
        <template #default="{ row }">
          {{ row.last_fetch_ts ? row.last_fetch_ts.slice(0, 10) : '从未' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleTest(row)">
            测试
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />

    <!-- 新增表单 -->
    <EmailConfigForm ref="formRef" />

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        新增邮箱
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCollectionStore } from '@/stores/collection'
import EmailConfigForm from './EmailConfigForm.vue'

const emit = defineEmits(['sync-bills'])

const collectionStore = useCollectionStore()

const visible = ref(false)
const emailConfigs = ref([])
const formRef = ref(null)
const saving = ref(false)

async function open() {
  visible.value = true
  await loadConfigs()
}

async function loadConfigs() {
  await collectionStore.loadEmailConfigs()
  emailConfigs.value = collectionStore.emailConfigs
}

async function handleTest(row) {
  try {
    const result = await collectionStore.testEmailConnection(row.id)
    if (result.success) {
      ElMessage.success('连接测试成功')
    } else {
      ElMessage.error(result.message || '连接测试失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '连接测试失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      '确定要删除此邮箱配置吗？',
      '确认删除',
      { type: 'warning' }
    )
    await collectionStore.deleteEmailConfig(row.id)
    ElMessage.success('已删除')
    await loadConfigs()
  } catch {
    // 取消
  }
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    const data = formRef.value.getFormData()
    await collectionStore.saveEmailConfig(data)
    ElMessage.success('邮箱配置新增成功')
    formRef.value.resetFields()
    await loadConfigs()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleClose() {
  formRef.value?.resetFields()
}

defineExpose({ open })
</script>
