<template>
  <div class="keyword-setting">
    <div class="action-bar keyword-toolbar">
      <div class="keyword-toolbar-main">
        <span class="keyword-toolbar-label">选择分类</span>
        <el-select
          v-model="selectedCategoryId"
          placeholder="选择分类"
          size="small"
          class="keyword-category-select"
          @change="loadKeywords"
        >
          <el-option v-for="c in enabledCategories" :key="c.id" :label="categoryLabel(c)" :value="c.id" />
        </el-select>
      </div>
      <div class="keyword-toolbar-actions">
        <el-button v-if="selectedCategoryId" type="primary" size="small" @click="addKeyword">
          <el-icon><Plus /></el-icon>
          新增规则
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="keyword-alert"
      title="当前关键词规则主要用于支出自动分类；收入账单会默认归入系统一级分类“收入”。"
    />

    <div v-if="selectedCategoryId" class="keyword-guide">
      <div class="keyword-guide-card">
        <div class="keyword-guide-title">匹配字段怎么选</div>
        <div class="keyword-guide-text">不用再区分“当前账单”和“发起方”。字段会自动同时参考账单本身和真实发起方文本。</div>
        <ul class="keyword-guide-list">
          <li><strong>全部文本</strong>：会一起检查交易对方、商品说明、备注，适合作为默认选择。</li>
          <li><strong>交易对方</strong>：适合商户名、收款方、对手方比较稳定的场景。</li>
          <li><strong>商品说明 / 备注</strong>：适合文本线索主要出现在说明或备注里的场景。</li>
        </ul>
      </div>
      <div class="keyword-guide-card">
        <div class="keyword-guide-title">权重与优先级</div>
        <ul class="keyword-guide-list">
          <li><strong>权重</strong>：命中后给分类增加多少分。越大，越容易把账单归到这个分类。</li>
          <li><strong>推荐默认值</strong>：普通规则建议先从 10 - 20 开始；像固定商户、品牌名这类强特征关键词，可以直接设到 30 以上。</li>
          <li><strong>优先级</strong>：当多个规则分数接近或同时命中时，优先级更高的规则更容易胜出。</li>
          <li><strong>优先级建议</strong>：大多数规则保持 0 就够用；只有当两个分类经常抢同一类账单时，再把更确定的规则调高到 5、10 这类更容易区分的值。</li>
          <li>实用建议：先把最明显、最确定的关键词权重设高；只有在多个关键词容易冲突时，再调整优先级。</li>
        </ul>
      </div>
      <div class="keyword-guide-card keyword-example-card">
        <div class="keyword-guide-title">可以这样写</div>
        <div class="keyword-example-list">
          <div class="keyword-example-item">
            <div class="keyword-example-scene">餐饮外卖</div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">字段</span>
              <span class="keyword-example-value">全部文本</span>
            </div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">关键词</span>
              <span class="keyword-example-value">美团、饿了么、外卖</span>
            </div>
          </div>
          <div class="keyword-example-item">
            <div class="keyword-example-scene">固定商户消费</div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">字段</span>
              <span class="keyword-example-value">交易对方</span>
            </div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">关键词</span>
              <span class="keyword-example-value">星巴克、瑞幸、盒马</span>
            </div>
          </div>
          <div class="keyword-example-item">
            <div class="keyword-example-scene">备注里才有线索</div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">字段</span>
              <span class="keyword-example-value">备注</span>
            </div>
            <div class="keyword-example-row">
              <span class="keyword-example-label">关键词</span>
              <span class="keyword-example-value">停车费、挂号、物业</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-table
      v-if="selectedCategoryId"
      :data="keywords"
      class="keyword-table"
      size="small"
      empty-text="暂无规则"
    >
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
          <template v-else>
            <div class="field-display">
              <div>{{ matchFieldLabel(row.match_field) }}</div>
              <div class="field-help">{{ matchFieldHelp(row.match_field) }}</div>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="权重" width="120">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.weight" size="small" :min="1" :max="999" />
          <template v-else>
            <div class="score-display">
              <div>{{ row.weight }}</div>
              <div class="score-help">命中加分</div>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="120">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.priority" size="small" :min="0" :max="999" />
          <template v-else>
            <div class="score-display">
              <div>{{ row.priority }}</div>
              <div class="score-help">冲突时更优先</div>
            </div>
          </template>
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
      <el-table-column label="操作" width="170" fixed="right">
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

function matchFieldHelp(field) {
  const item = systemStore.categoryMatchFields.find(f => f.field_key === field)
  return item?.help_text || ''
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

<style scoped>
.keyword-setting {
  min-width: 0;
}

.keyword-toolbar {
  align-items: flex-end;
}

.keyword-toolbar-main {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.keyword-toolbar-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
  white-space: nowrap;
}

.keyword-category-select {
  width: min(360px, 100%);
}

.keyword-toolbar-actions {
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.keyword-alert {
  margin-bottom: 12px;
}

.keyword-guide {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.keyword-guide-card {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-lg);
  background: var(--bg-card-subtle);
}

.keyword-guide-title {
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  font-weight: 700;
  margin-bottom: var(--spacing-sm);
}

.keyword-guide-text,
.field-help,
.score-help {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.keyword-guide-list {
  margin: var(--spacing-sm) 0 0;
  padding-left: 18px;
  color: var(--color-text-regular);
  font-size: var(--font-size-small);
  line-height: 1.7;
}

.keyword-example-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-sm);
}

.keyword-example-item {
  min-width: 0;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color-lighter);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
}

.keyword-example-scene {
  margin-bottom: 8px;
  color: var(--color-text-primary);
  font-size: var(--font-size-small);
  font-weight: 700;
}

.keyword-example-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.keyword-example-row + .keyword-example-row {
  margin-top: 4px;
}

.keyword-example-label {
  flex: 0 0 32px;
  color: var(--color-text-tertiary);
}

.keyword-example-value {
  min-width: 0;
}

.keyword-table {
  width: 100%;
}

.field-display,
.score-display {
  display: grid;
  gap: 2px;
}

.keyword-table :deep(.el-input),
.keyword-table :deep(.el-select),
.keyword-table :deep(.el-input-number) {
  width: 100%;
}

@media (max-width: 1200px) {
  .keyword-toolbar {
    align-items: stretch;
  }

  .keyword-toolbar-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .keyword-guide {
    grid-template-columns: 1fr;
  }
}
</style>
