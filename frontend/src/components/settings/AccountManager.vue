<template>
  <div>
    <div class="action-bar">
      <div style="display: flex; gap: 8px">
        <el-select v-model="roleFilter" placeholder="所属角色" clearable size="small" @change="loadAccounts">
          <el-option v-for="r in allRoles" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-button
          v-if="selectedAccountIds.length > 0"
          type="primary"
          size="small"
          @click="openBatchDialog"
        >
          批量分配角色 ({{ selectedAccountIds.length }})
        </el-button>
      </div>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建账户
      </el-button>
    </div>

    <el-table
      ref="tableRef"
      :data="systemStore.accounts"
      style="width: 100%"
      size="small"
      empty-text="暂无账户"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="account_name" label="账户名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="account_tag" label="账户标识" width="140" show-overflow-tooltip />
      <el-table-column label="渠道" width="80">
        <template #default="{ row }">
          <el-tag size="small">{{ channelLabel(row.channel) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="所属角色" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.role_name || getRoleName(row.role_id) }}
        </template>
      </el-table-column>
      <el-table-column label="规范账户" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <el-tag v-if="row.merged_into_account_id" size="small" type="warning">
            已归并至 {{ row.canonical_account_name || row.merged_into_account_id }}
          </el-tag>
          <span v-else>自身</span>
        </template>
      </el-table-column>
      <el-table-column label="曾用名" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.channel === 'wechat'" size="small" type="info">{{ row.alias_count || 0 }} 个</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button v-if="row.channel === 'wechat'" link type="success" size="small" @click="openAliasDialog(row)">曾用名</el-button>
          <el-button v-if="row.channel === 'wechat'" link type="warning" size="small" @click="openMergeDialog(row)">合并</el-button>
          <el-button v-if="row.merged_into_account_id" link type="info" size="small" @click="handleUnmerge(row)">取消合并</el-button>
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

    <el-dialog v-model="batchDialogVisible" title="批量分配角色" width="450px">
      <p style="margin-bottom: 12px">
        将选中的 {{ selectedAccountIds.length }} 个账户分配到新角色，并同步更新关联账单的角色归属。
      </p>
      <el-select v-model="batchRoleId" placeholder="选择目标角色" style="width: 100%">
        <el-option v-for="r in allRoles" :key="r.id" :label="r.name" :value="r.id" />
      </el-select>
      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSaving" :disabled="!batchRoleId" @click="handleBatchAssign">
          确认分配
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="aliasDialogVisible" :title="`${currentAccount?.account_name || ''} - 微信曾用名`" width="480px">
      <div style="display:flex; gap:8px; margin-bottom:12px">
        <el-input v-model="aliasValue" placeholder="输入微信曾用名/昵称" maxlength="30" />
        <el-button type="primary" :loading="aliasSaving" @click="handleAddAlias">添加</el-button>
      </div>
      <el-table :data="aliases" size="small" empty-text="暂无曾用名">
        <el-table-column prop="alias_value" label="曾用名" />
        <el-table-column prop="alias_type" label="类型" width="130" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleDeleteAlias(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="mergeDialogVisible" :title="`${currentAccount?.account_name || ''} - 合并微信账户`" width="520px">
      <p style="margin-bottom: 12px">
        逻辑归并不会删除源账户，也不会批量改写历史账单角色；后续导入和展示默认解析到目标规范账户。
      </p>
      <el-select v-model="mergeTargetId" placeholder="选择目标规范账户" filterable style="width: 100%">
        <el-option
          v-for="acc in mergeTargetOptions"
          :key="acc.id"
          :label="`${acc.account_name} (${acc.account_tag})`"
          :value="acc.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="mergeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="mergeSaving" :disabled="!mergeTargetId" @click="handleMergeAccount">
          确认合并
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="unmergeDialogVisible" :title="`${currentAccount?.account_name || ''} - 取消合并`" width="560px">
      <p style="margin-bottom: 12px">
        取消合并会先解除该账户到规范账户的逻辑归并。以下恢复项可按需选择：
      </p>
      <el-checkbox v-model="unmergeOptions.remove_auto_added_target_aliases">
        同时删除合并时自动加入目标账户的曾用名
      </el-checkbox>
      <br />
      <el-checkbox v-model="unmergeOptions.return_source_aliases">
        同时把由源账户迁移到目标账户的曾用名归还源账户
      </el-checkbox>
      <br />
      <el-checkbox v-model="unmergeOptions.retrace_related_bills">
        重新进行相关账单的真实支付者溯源
      </el-checkbox>
      <p class="hint-text">
        重新溯源可能改变相关账单的真实支付者归属，请确认后执行。
      </p>
      <template #footer>
        <el-button @click="unmergeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="unmergeSaving" @click="handleUnmergeConfirm">
          确认取消合并
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const saving = ref(false)
const batchSaving = ref(false)
const dialogVisible = ref(false)
const batchDialogVisible = ref(false)
const editingId = ref(null)
const roleFilter = ref(null)
const formRef = ref(null)
const tableRef = ref(null)
const allRoles = ref([])
const selectedAccountIds = ref([])
const batchRoleId = ref(null)
const aliasDialogVisible = ref(false)
const aliasSaving = ref(false)
const aliases = ref([])
const aliasValue = ref('')
const currentAccount = ref(null)
const mergeDialogVisible = ref(false)
const mergeSaving = ref(false)
const mergeTargetId = ref(null)
const unmergeDialogVisible = ref(false)
const unmergeSaving = ref(false)
const unmergeOptions = reactive({
  remove_auto_added_target_aliases: false,
  return_source_aliases: false,
  retrace_related_bills: false,
})

const mergeTargetOptions = computed(() => systemStore.accounts.filter(acc => (
  acc.channel === 'wechat'
  && acc.id !== currentAccount.value?.id
  && !acc.merged_into_account_id
)))

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
  formRef.value?.clearValidate?.()
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

function handleSelectionChange(rows) {
  selectedAccountIds.value = rows.map(row => row.id)
}

function openBatchDialog() {
  batchRoleId.value = null
  batchDialogVisible.value = true
}

async function handleBatchAssign() {
  if (!batchRoleId.value || selectedAccountIds.value.length === 0) return

  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${selectedAccountIds.value.length} 个账户批量分配到新角色吗？这会同步更新关联账单的角色归属。`,
      '确认批量分配',
      { type: 'warning', confirmButtonText: '确认分配', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  batchSaving.value = true
  try {
    const result = await systemStore.batchAssignAccountRole(selectedAccountIds.value, batchRoleId.value)
    ElMessage.success(`已更新 ${result.updated_count} 个账户`)
    batchDialogVisible.value = false
    selectedAccountIds.value = []
    tableRef.value?.clearSelection()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batchSaving.value = false
  }
}

async function openAliasDialog(row) {
  currentAccount.value = row
  aliasValue.value = ''
  aliases.value = await systemStore.loadAccountAliases(row.id)
  aliasDialogVisible.value = true
}

async function handleAddAlias() {
  if (!currentAccount.value || !aliasValue.value.trim()) return
  aliasSaving.value = true
  try {
    await systemStore.createAccountAlias(currentAccount.value.id, aliasValue.value.trim())
    aliases.value = await systemStore.loadAccountAliases(currentAccount.value.id)
    aliasValue.value = ''
    await loadAccounts()
    ElMessage.success('曾用名已添加')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aliasSaving.value = false
  }
}

async function handleDeleteAlias(row) {
  try {
    await systemStore.deleteAccountAlias(row.id)
    aliases.value = await systemStore.loadAccountAliases(currentAccount.value.id)
    await loadAccounts()
    ElMessage.success('曾用名已删除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openMergeDialog(row) {
  currentAccount.value = row
  mergeTargetId.value = null
  mergeDialogVisible.value = true
}

async function handleMergeAccount() {
  if (!currentAccount.value || !mergeTargetId.value) return
  try {
    await ElMessageBox.confirm('确认将该微信账户逻辑归并到目标规范账户？历史账单不会被删除。', '确认合并', { type: 'warning' })
  } catch { return }

  mergeSaving.value = true
  try {
    await systemStore.mergeWechatAccounts(currentAccount.value.id, mergeTargetId.value)
    mergeDialogVisible.value = false
    ElMessage.success('微信账户已逻辑归并')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    mergeSaving.value = false
  }
}

async function handleUnmerge(row) {
  currentAccount.value = row
  unmergeOptions.remove_auto_added_target_aliases = false
  unmergeOptions.return_source_aliases = false
  unmergeOptions.retrace_related_bills = false
  unmergeDialogVisible.value = true
}

async function handleUnmergeConfirm() {
  if (!currentAccount.value) return
  unmergeSaving.value = true
  try {
    const result = await systemStore.unmergeWechatAccount(currentAccount.value.id, { ...unmergeOptions })
    unmergeDialogVisible.value = false
    const retrace = result?.retrace
    const retraceText = retrace ? `；重溯源 ${retrace.bills_retraced} 条，成功 ${retrace.merged_count} 条` : ''
    ElMessage.success(`已取消合并，删除曾用名 ${result?.removed_alias_count || 0} 个，归还曾用名 ${result?.returned_alias_count || 0} 个${retraceText}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    unmergeSaving.value = false
  }
}

function getRoleName(roleId) {
  if (!roleId) return '-'
  const role = allRoles.value.find(r => r.id === roleId)
  return role?.name || '-'
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

<style scoped>
.hint-text {
  margin-top: 12px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}
</style>
