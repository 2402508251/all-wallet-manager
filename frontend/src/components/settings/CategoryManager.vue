<template>
  <div>
    <div class="action-bar">
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建分类
      </el-button>
    </div>

    <el-table :data="systemStore.categories" style="width: 100%" size="small" empty-text="暂无分类">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="icon" label="图标" width="70" />
      <el-table-column label="父分类" width="100">
        <template #default="{ row }">
          {{ parentName(row.parent_id) || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑分类' : '新建分类'" width="450px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="如 餐饮美食" maxlength="20" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="如 🍽️" maxlength="10" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-select v-model="form.parent_id" placeholder="无（顶级分类）" clearable>
            <el-option
              v-for="c in topLevelCategories"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
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
const formRef = ref(null)

const form = reactive({
  name: '',
  icon: '',
  parent_id: null,
  sort_order: 0,
})

const rules = {
  name: [
    { required: true, message: '请输入分类名称', trigger: 'blur' },
    { max: 20, message: '名称不超过20字', trigger: 'blur' },
  ],
}

const topLevelCategories = computed(() =>
  systemStore.categories.filter(c => !c.parent_id)
)

onMounted(() => {
  systemStore.loadCategories()
})

function parentName(id) {
  if (!id) return null
  const c = systemStore.categories.find(c => c.id === id)
  return c?.name || null
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.name = row.name
    form.icon = row.icon || ''
    form.parent_id = row.parent_id || null
    form.sort_order = row.sort_order || 0
  } else {
    editingId.value = null
    form.name = ''
    form.icon = ''
    form.parent_id = null
    form.sort_order = 0
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
      await systemStore.updateCategory(editingId.value, { ...form })
      ElMessage.success('分类已更新')
    } else {
      await systemStore.createCategory({
        name: form.name,
        icon: form.icon,
        parent_id: form.parent_id,
      })
      ElMessage.success('分类已创建')
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
    await ElMessageBox.confirm(`确定要删除分类"${row.name}"吗？`, '确认删除', { type: 'warning' })
    await systemStore.deleteCategory(row.id)
    ElMessage.success('分类已删除')
  } catch { /* 取消 */ }
}
</script>
