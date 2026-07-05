<template>
  <div>
    <div class="action-bar">
      <div>
        <el-select v-model="roleFilter" placeholder="所属角色" clearable size="small" @change="loadAccounts">
          <el-option v-for="r in allRoles" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </div>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建账户
      </el-button>
    </div>

    <el-table :data="systemStore.accounts" style="width: 100%" size="small" empty-text="暂无账户">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="account_name" label="账户名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="account_tag" label="账户标识" width="140" show-overflow-tooltip />
      <el-table-column label="渠道" width="80">
        <template #default="{ row }">
          <el-tag size="small">{{ channelLabel(row.channel) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑账户' : '新建账户'" width="450px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账户名称" prop="account_name">
          <el-input v-model="form.account_name" placeholder="如 微信-风-零钱" maxlength="30" />
        </el-form-item>
        <el-form-item label="账户标识" prop="account_tag">
          <el-input v-model="form.account_tag" placeholder="如 wechat-风" />
        </el-form-item>
        <el-form-item label="渠道" prop="channel">
          <el-select v-model="form.channel" placeholder="选择渠道">
            <el-option label="微信" value="wechat" />
            <el-option label="支付宝" value="alipay" />
            <el-option label="建行" value="ccb" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属角色" prop="role_id">
          <el-select v-model="form.role_id" placeholder="选择角色">
            <el-option v-for="r in allRoles" :key="r.id" :label="`${r.name}`" :value="r.id" />
          </el-select>
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
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const roleFilter = ref(null)
const formRef = ref(null)
const allRoles = ref([])

const form = reactive({
  account_name: '',
  account_tag: '',
  channel: '',
  role_id: null,
})

const rules = {
  account_name: [
    { required: true, message: '请输入账户名称', trigger: 'blur' },
    { max: 30, message: '名称不超过30字', trigger: 'blur' },
  ],
  account_tag: [
    { required: true, message: '请输入账户标识', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9一-龥\-_]+$/, message: '仅支持中英文、数字、横杠、下划线', trigger: 'blur' },
  ],
  channel: [{ required: true, message: '请选择渠道', trigger: 'change' }],
  role_id: [{ required: true, message: '请选择所属角色', trigger: 'change' }],
}

onMounted(async () => {
  await loadAllRoles()
  await loadAccounts()
})

async function loadAllRoles() {
  await systemStore.loadRoles(null)
  allRoles.value = systemStore.roles
}

async function loadAccounts() {
  const rid = roleFilter.value
  systemStore.currentRoleId = rid
  await systemStore.loadAccounts(rid)
  // Ensure all roles are loaded for dropdown
  if (allRoles.value.length === 0) {
    await loadAllRoles()
  }
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.account_name = row.account_name
    form.account_tag = row.account_tag
    form.channel = row.channel
    form.role_id = row.role_id
  } else {
    editingId.value = null
    form.account_name = ''
    form.account_tag = ''
    form.channel = ''
    form.role_id = null
  }
  dialogVisible.value = true
}

function resetForm() {
  editingId.value = null
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    if (editingId.value) {
      await systemStore.updateAccount(editingId.value, { ...form })
      ElMessage.success('账户已更新')
    } else {
      await systemStore.createAccount({ ...form })
      ElMessage.success('账户已创建')
    }
    dialogVisible.value = false
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function channelLabel(ch) {
  const map = { wechat: '微信', alipay: '支付宝', ccb: '建行' }
  return map[ch] || ch
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除账户"${row.account_name}"吗？`, '确认删除', { type: 'warning' })
    await systemStore.deleteAccount(row.id)
    ElMessage.success('账户已删除')
  } catch { /* 取消 */ }
}
</script>
