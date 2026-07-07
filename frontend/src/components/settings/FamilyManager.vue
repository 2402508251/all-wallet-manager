<template>
  <div>
    <div class="action-bar">
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建家庭
      </el-button>
    </div>

    <el-table v-loading="loading" :data="systemStore.families" style="width: 100%" size="small"
      empty-text="暂无家庭">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column label="角色数量" width="100">
        <template #default="{ row }">
          {{ row.role_count || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑家庭' : '新建家庭'" width="400px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules">
        <el-form-item label="家庭名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入家庭名称" maxlength="20" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const form = reactive({ name: '' })
const rules = {
  name: [
    { required: true, message: '请输入家庭名称', trigger: 'blur' },
    { max: 20, message: '名称不超过20字', trigger: 'blur' },
  ],
}

onMounted(() => {
  systemStore.loadFamilies()
})

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.name = row.name
  } else {
    editingId.value = null
    form.name = ''
  }
  dialogVisible.value = true
}

function resetForm() {
  editingId.value = null
  form.name = ''
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    if (editingId.value) {
      await systemStore.updateFamily(editingId.value, { name: form.name })
      ElMessage.success('家庭已更新')
    } else {
      await systemStore.createFamily(form.name)
      ElMessage.success('家庭已创建')
    }
    dialogVisible.value = false
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除家庭"${row.name}"吗？`, '确认删除', { type: 'warning' })
    await systemStore.deleteFamily(row.id)
    ElMessage.success('家庭已删除')
  } catch { /* 取消 */ }
}
</script>
