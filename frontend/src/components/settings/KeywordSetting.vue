<template>
  <div>
    <div class="action-bar">
      <div>
        <span style="margin-right:8px">选择分类:</span>
        <el-select v-model="selectedCategoryId" placeholder="选择分类" size="small" @change="loadKeywords">
          <el-option v-for="c in enabledCategories" :key="c.id" :label="categoryLabel(c)" :value="c.id" />
        </el-select>
      </div>
      <el-button v-if="selectedCategoryId" type="primary" size="small" @click="addKeyword">
        <el-icon><Plus /></el-icon>
        新增规则
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      title="当前关键词规则主要用于支出自动分类；收入账单会默认归入系统一级分类“收入”。"
    />

    <el-table v-if="selectedCategoryId" :data="keywords" style="width: 100%" size="small" empty-text="暂无规则">
      <el-table-column label="关键词" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="row._editing" v-model="row.keyword" size="small" maxlength="40" />
          <template v-else>{{ row.keyword }}</template>
        </template>
      </el-table-column>
      <el-table-column label="匹配字段" min-width="160">
        <template #default="{ row }">
          <el-select v-if="row._editing" v-model="row.match_field" size="small">
            <el-option v-for="f in enabledFields" :key="f.field_key" :label="f.label" :value="f.field_key" />
          </el-select>
          <template v-else>{{ matchFieldLabel(row.match_field) }}</template>
        </template>
      </el-table-column>
      <el-table-column label="权重" width="100">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.weight" size="small" :min="1" :max="999" />
          <template v-else>{{ row.weight }}</template>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="100">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.priority" size="small" :min="0" :max="999" />
          <template v-else>{{ row.priority }}</template>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-switch v-if="row._editing" v-model="row.is_enabled" :active-value="1" :inactive-value="0" />
          <el-tag v-else size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source === 'system' ? 'info' : 'warning'">{{ row.source === 'system' ? '系统' : '用户' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row, $index }">
          <template v-if="row._editing">
            <el-button link type="success" size="small" @click="saveKeywordRow($index)">保存</el-button>
            <el-button link type="info" size="small" @click="cancelEdit($index)">取消</el-button>
          </template>
          <template v-else>
            <el-button link type="primary" size="small" @click="editKeyword($index)">编辑</el-button>
            <el-button link type="danger" size="small" :disabled="row.source === 'system'" @click="removeKeyword($index)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!selectedCategoryId" description="请先选择一个分类" :image-size="80" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const selectedCategoryId = ref(null)
const keywords = ref([])

const enabledCategories = computed(() => systemStore.categories.filter(c => c.is_enabled !== 0))
const enabledFields = computed(() => systemStore.categoryMatchFields.filter(f => f.is_enabled !== 0))

onMounted(async () => {
  if (!systemStore.categories.length) await systemStore.loadCategories()
  await systemStore.loadCategoryMatchFields()
})

async function loadKeywords() {
  if (!selectedCategoryId.value) return
  await systemStore.loadCategoryKeywords(selectedCategoryId.value)
  keywords.value = systemStore.categoryKeywords.map(k => ({ ...k, _editing: false, _original: { ...k } }))
}

function categoryLabel(category) {
  const prefix = category.parent_id ? '└ ' : ''
  return `${prefix}${category.name}`
}

function matchFieldLabel(field) {
  const item = systemStore.categoryMatchFields.find(f => f.field_key === field)
  return item?.label || field
}

function addKeyword() {
  keywords.value.push({
    id: null,
    keyword: '',
    match_field: enabledFields.value[0]?.field_key || 'counterparty',
    weight: 10,
    priority: 0,
    match_mode: 'contains',
    is_enabled: 1,
    source: 'user',
    _editing: true,
    _new: true,
  })
}

function editKeyword(index) {
  keywords.value[index]._editing = true
  keywords.value[index]._original = { ...keywords.value[index] }
}

function cancelEdit(index) {
  if (keywords.value[index]._new) {
    keywords.value.splice(index, 1)
    return
  }
  const orig = keywords.value[index]._original
  keywords.value[index] = { ...orig, _editing: false, _original: { ...orig } }
}

function saveKeywordRow(index) {
  if (!keywords.value[index].keyword?.trim()) {
    ElMessage.error('请输入关键词')
    return
  }
  keywords.value[index]._editing = false
  keywords.value[index]._new = false
  saveAllKeywords()
}

function removeKeyword(index) {
  if (keywords.value[index].source === 'system') return
  keywords.value.splice(index, 1)
  saveAllKeywords()
}

async function saveAllKeywords() {
  if (!selectedCategoryId.value) return
  const data = keywords.value.map(k => ({
    keyword: k.keyword,
    match_field: k.match_field,
    weight: k.weight ?? 10,
    priority: k.priority ?? 0,
    match_mode: k.match_mode || 'contains',
    is_enabled: k.is_enabled ?? 1,
    source: k.source || 'user',
  }))
  try {
    await systemStore.saveCategoryKeywords(selectedCategoryId.value, data)
    ElMessage.success('分类规则已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>
