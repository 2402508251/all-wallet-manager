<template>
  <div>
    <div class="action-bar">
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>
        新建分类
      </el-button>
    </div>

    <el-table
      :data="categoryRows"
      row-key="id"
      style="width: 100%"
      size="small"
      empty-text="暂无分类"
    >
      <el-table-column label="分类" min-width="180">
        <template #default="{ row }">
          <span :style="{ paddingLeft: row.level === 2 ? '20px' : '0' }">
            <span v-if="row.level === 2">└ </span>{{ row.icon }} {{ row.name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="层级" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.level === 1 ? 'primary' : 'success'">
            {{ row.level === 1 ? '一级' : '二级' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source === 'system' ? 'info' : 'warning'">
            {{ row.source === 'system' ? '系统' : '用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">
            {{ row.is_enabled ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="70" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          <el-button link type="danger" size="small" :disabled="row.source === 'system'" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑分类' : '新建分类'" width="460px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="如 咖啡饮品" maxlength="20" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="如 ☕" maxlength="10" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-select v-model="form.parent_id" placeholder="无（一级分类）" clearable :disabled="editingHasChildren">
            <el-option v-for="c in topLevelCategories" :key="c.id" :label="c.name" :value="c.id" :disabled="c.id === editingId" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_enabled" :active-value="1" :inactive-value="0" />
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
  is_enabled: 1,
})

const rules = {
  name: [
    { required: true, message: '请输入分类名称', trigger: 'blur' },
    { max: 20, message: '名称不超过20字', trigger: 'blur' },
  ],
}

const topLevelCategories = computed(() =>
  systemStore.categories.filter(c => Number(c.level || (c.parent_id ? 2 : 1)) === 1)
)

const editingHasChildren = computed(() =>
  editingId.value && systemStore.categories.some(c => c.parent_id === editingId.value)
)

const categoryRows = computed(() => {
  const top = [...topLevelCategories.value].sort(sortCategory)
  const rows = []
  for (const item of top) {
    rows.push(item)
    rows.push(...systemStore.categories
      .filter(c => c.parent_id === item.id)
      .sort(sortCategory))
  }
  return rows
})

onMounted(() => {
  systemStore.loadCategories()
})

function sortCategory(a, b) {
  return (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.name = row.name
    form.icon = row.icon || ''
    form.parent_id = row.parent_id || null
    form.sort_order = row.sort_order || 0
    form.is_enabled = row.is_enabled ?? 1
  } else {
    editingId.value = null
    form.name = ''
    form.icon = ''
    form.parent_id = null
    form.sort_order = 0
    form.is_enabled = 1
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
      await systemStore.createCategory({ ...form })
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
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  }
}
</script>
