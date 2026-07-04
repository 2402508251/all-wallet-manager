<template>
  <div>
    <div class="action-bar">
      <el-button type="primary" size="small" @click="showForm = true">
        <el-icon><Plus /></el-icon>
        新建邮箱配置
      </el-button>
    </div>

    <el-table :data="systemStore.emails" style="width: 100%" size="small" empty-text="暂无邮箱配置">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="email_addr" label="邮箱地址" min-width="180" />
      <el-table-column prop="imap_server" label="IMAP服务器" width="150" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :loading="testingId === row.id" @click="handleTest(row)">
            测试
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增表单 -->
    <div v-if="showForm" class="card-box" style="margin-top:16px">
      <h4 style="margin-bottom:12px">新增邮箱配置</h4>
      <EmailConfigForm ref="formRef" />
      <div style="margin-top:12px;text-align:right">
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">确认新增</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'
import EmailConfigForm from '@/components/collection/EmailConfigForm.vue'

const systemStore = useSystemStore()
const formRef = ref(null)
const showForm = ref(false)
const saving = ref(false)
const testingId = ref(null)

onMounted(() => {
  systemStore.loadEmails()
})

async function handleTest(row) {
  testingId.value = row.id
  try {
    const result = await systemStore.testEmailConnection(row.id)
    if (result.success) {
      ElMessage.success('连接测试成功')
    } else {
      ElMessage.error(result.message || '连接测试失败')
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testingId.value = null
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除邮箱配置"${row.email_addr}"吗？`, '确认删除', { type: 'warning' })
    await systemStore.deleteEmail(row.id)
    ElMessage.success('邮箱配置已删除')
  } catch { /* 取消 */ }
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    const data = formRef.value.getFormData()
    await systemStore.saveEmail(data)
    ElMessage.success('邮箱配置新增成功')
    showForm.value = false
    formRef.value.resetFields()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>
