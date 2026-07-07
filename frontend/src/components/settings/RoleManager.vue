<template>
  <div>
    <div class="action-bar">
      <div>
        <el-select v-model="familyFilter" placeholder="所属家庭" clearable size="small" @change="loadRoles">
          <el-option v-for="f in systemStore.families" :key="f.id" :label="f.name" :value="f.id" />
        </el-select>
      </div>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建角色
      </el-button>
    </div>

    <el-table :data="systemStore.roles" style="width: 100%" size="small" empty-text="暂无角色">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role_type === 'shared' ? 'warning' : ''">
            {{ row.role_type === 'shared' ? '共享' : '个人' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关联家庭" min-width="220">
        <template #default="{ row }">
          <template v-if="roleFamilyMap[row.id]">
            <el-tag
              v-for="rf in roleFamilyMap[row.id]"
              :key="rf.family_id"
              size="small"
              type="info"
              style="margin-right: 4px"
            >
              {{ rf.family_name || `家庭#${rf.family_id}` }}
            </el-tag>
          </template>
          <span v-else style="color: var(--color-text-secondary)">未关联</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button link type="primary" size="small" @click="openFamilyDialog(row)">家庭</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑角色' : '新建角色'" width="450px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="如 本人、配偶" maxlength="20" />
        </el-form-item>
        <el-form-item label="关联家庭">
          <el-select v-model="form.family_ids" placeholder="选择家庭" clearable multiple collapse-tags collapse-tags-tooltip>
            <el-option v-for="f in systemStore.families" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色类型">
          <el-radio-group v-model="form.role_type">
            <el-radio value="personal">个人</el-radio>
            <el-radio value="shared">共享</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="familyDialogVisible" title="管理角色-家庭关联" width="500px">
      <div v-if="editingRole">
        <div style="margin-bottom: 12px">
          <strong>{{ editingRole.name }}</strong> 关联的家庭：
        </div>
        <el-table :data="currentRoleFamilies" size="small" empty-text="暂无关联家庭">
          <el-table-column prop="family_name" label="家庭名称" min-width="120" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button
                link type="danger" size="small"
                @click="handleRemoveFamily(row)"
              >移除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />

        <div style="display: flex; gap: 8px; align-items: center">
          <el-select v-model="addFamilyId" placeholder="选择家庭" size="small" style="flex: 1">
            <el-option
              v-for="f in availableFamilies"
              :key="f.id"
              :label="f.name"
              :value="f.id"
            />
          </el-select>
          <el-button type="primary" size="small" @click="handleAddFamily">添加关联</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="familyDialogVisible = false">关闭</el-button>
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
const familyDialogVisible = ref(false)
const editingId = ref(null)
const editingRole = ref(null)
const familyFilter = ref(null)
const formRef = ref(null)
const roleFamilyMap = ref({})
const currentRoleFamilies = ref([])
const addFamilyId = ref(null)

const form = reactive({
  name: '',
  family_ids: [],
  role_type: 'personal',
})

const rules = {
  name: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { max: 20, message: '名称不超过20字', trigger: 'blur' },
  ],
}

const availableFamilies = computed(() => {
  const linkedIds = currentRoleFamilies.value.map(rf => rf.family_id)
  return systemStore.families.filter(f => !linkedIds.includes(f.id))
})

onMounted(() => {
  systemStore.loadFamilies()
  loadRoles()
})

async function loadRoles() {
  const fid = familyFilter.value
  systemStore.currentFamilyId = fid
  await systemStore.loadRoles(fid)
  await loadRoleFamilyMap()
}

async function loadRoleFamilyMap() {
  const map = {}
  for (const role of systemStore.roles) {
    try {
      const families = await systemStore.getRoleFamilies(role.id)
      map[role.id] = families
    } catch {
      map[role.id] = []
    }
  }
  roleFamilyMap.value = map
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.name = row.name
    const families = roleFamilyMap.value[row.id] || []
    form.family_ids = families.map(rf => rf.family_id)
    form.role_type = row.role_type || 'personal'
  } else {
    editingId.value = null
    form.name = ''
    form.family_ids = []
    form.role_type = 'personal'
  }
  dialogVisible.value = true
}

function resetForm() {
  editingId.value = null
}

async function openFamilyDialog(row) {
  editingRole.value = row
  addFamilyId.value = null
  try {
    currentRoleFamilies.value = await systemStore.getRoleFamilies(row.id)
  } catch {
    currentRoleFamilies.value = []
  }
  familyDialogVisible.value = true
}

async function handleAddFamily() {
  if (!addFamilyId.value) {
    ElMessage.warning('请选择家庭')
    return
  }
  try {
    await systemStore.addRoleFamily(editingRole.value.id, addFamilyId.value)
    currentRoleFamilies.value = await systemStore.getRoleFamilies(editingRole.value.id)
    addFamilyId.value = null
    ElMessage.success('已添加关联')
    await loadRoleFamilyMap()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleRemoveFamily(rf) {
  try {
    await ElMessageBox.confirm(
      `确定要移除与"${rf.family_name || '家庭#' + rf.family_id}"的关联吗？`,
      '确认移除',
      { type: 'warning' },
    )
    await systemStore.removeRoleFamily(editingRole.value.id, rf.family_id)
    currentRoleFamilies.value = await systemStore.getRoleFamilies(editingRole.value.id)
    ElMessage.success('已移除关联')
    await loadRoleFamilyMap()
  } catch { /* 取消 */ }
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    if (editingId.value) {
      await systemStore.updateRole(editingId.value, {
        name: form.name,
        role_type: form.role_type,
      })

      const existingFamilies = await systemStore.getRoleFamilies(editingId.value)
      const existingIds = existingFamilies.map(rf => rf.family_id)
      const targetIds = form.family_ids

      for (const familyId of targetIds) {
        if (!existingIds.includes(familyId)) {
          await systemStore.addRoleFamily(editingId.value, familyId)
        }
      }

      for (const familyId of existingIds) {
        if (!targetIds.includes(familyId)) {
          await systemStore.removeRoleFamily(editingId.value, familyId)
        }
      }

      ElMessage.success('角色已更新')
    } else {
      const result = await systemStore.createRole({
        name: form.name,
        family_id: form.family_ids[0] ?? null,
        role_type: form.role_type,
      })

      const roleId = result?.role_id
      if (roleId) {
        for (const familyId of form.family_ids.slice(1)) {
          await systemStore.addRoleFamily(roleId, familyId)
        }
      }

      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
    await loadRoles()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定要删除角色"${row.name}"吗？`, '确认删除', { type: 'warning' })
    await systemStore.deleteRole(row.id)
    ElMessage.success('角色已删除')
    await loadRoleFamilyMap()
  } catch { /* 取消 */ }
}
</script>