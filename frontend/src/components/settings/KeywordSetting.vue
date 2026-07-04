<template>
  <div>
    <div class="action-bar">
      <div>
        <span style="margin-right:8px">选择分类:</span>
        <el-select v-model="selectedCategoryId" placeholder="选择分类" size="small" @change="loadKeywords">
          <el-option v-for="c in systemStore.categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
      <el-button v-if="selectedCategoryId" type="primary" size="small" @click="addKeyword">
        <el-icon><Plus /></el-icon>
        新增关键词
      </el-button>
    </div>

    <el-table v-if="selectedCategoryId" :data="keywords" style="width: 100%" size="small"
      empty-text="暂无关键词">
      <el-table-column label="关键词" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="row._editing" v-model="row.keyword" size="small" maxlength="20" />
          <template v-else>{{ row.keyword }}</template>
        </template>
      </el-table-column>
      <el-table-column label="匹配字段" width="140">
        <template #default="{ row }">
          <el-select v-if="row._editing" v-model="row.match_field" size="small">
            <el-option label="交易对方" value="counterparty" />
            <el-option label="商品说明" value="product_desc" />
            <el-option label="备注" value="remark" />
          </el-select>
          <template v-else>{{ matchFieldLabel(row.match_field) }}</template>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="80">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.priority" size="small" :min="1" :max="99" />
          <template v-else>{{ row.priority }}</template>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row, $index }">
          <template v-if="row._editing">
            <el-button link type="success" size="small" @click="saveKeywordRow($index)">保存</el-button>
            <el-button link type="info" size="small" @click="cancelEdit($index)">取消</el-button>
          </template>
          <template v-else>
            <el-button link type="primary" size="small" @click="editKeyword($index)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeKeyword($index)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!selectedCategoryId" description="请先选择一个分类" :image-size="80" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const selectedCategoryId = ref(null)
const keywords = ref([])

async function loadKeywords() {
  if (!selectedCategoryId.value) return
  await systemStore.loadCategoryKeywords(selectedCategoryId.value)
  keywords.value = systemStore.categoryKeywords.map(k => ({ ...k, _editing: false, _original: { ...k } }))
}

function matchFieldLabel(field) {
  const map = { counterparty: '交易对方', product_desc: '商品说明', remark: '备注' }
  return map[field] || field
}

function addKeyword() {
  keywords.value.push({
    id: null,
    keyword: '',
    match_field: 'counterparty',
    priority: 0,
    _editing: true,
    _new: true,
  })
}

function editKeyword(index) {
  keywords.value[index]._editing = true
  keywords.value[index]._original = {
    keyword: keywords.value[index].keyword,
    match_field: keywords.value[index].match_field,
    priority: keywords.value[index].priority,
  }
}

function cancelEdit(index) {
  if (keywords.value[index]._new) {
    keywords.value.splice(index, 1)
    return
  }
  const orig = keywords.value[index]._original
  keywords.value[index].keyword = orig.keyword
  keywords.value[index].match_field = orig.match_field
  keywords.value[index].priority = orig.priority
  keywords.value[index]._editing = false
}

function saveKeywordRow(index) {
  keywords.value[index]._editing = false
  keywords.value[index]._new = false
  saveAllKeywords()
}

function removeKeyword(index) {
  keywords.value.splice(index, 1)
  saveAllKeywords()
}

async function saveAllKeywords() {
  if (!selectedCategoryId.value) return
  const data = keywords.value.map(k => ({
    keyword: k.keyword,
    match_field: k.match_field,
    priority: k.priority,
  }))
  try {
    await systemStore.saveCategoryKeywords(selectedCategoryId.value, data)
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>
