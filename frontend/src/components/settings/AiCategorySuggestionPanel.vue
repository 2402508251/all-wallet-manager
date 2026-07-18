<template>
  <div class="ai-category-panel">
    <div class="panel-head">
      <div>
        <div class="section-title">AI 关键词建议</div>
        <div class="section-subtitle">基于账单样本生成分类规则草稿，审核后写入当前分类。</div>
      </div>
      <el-button size="small" @click="loadHistory">刷新历史</el-button>
    </div>

    <div class="sample-box">
      <el-radio-group v-model="sampleMode" size="small">
        <el-radio-button label="manual">手动样本</el-radio-button>
        <el-radio-button label="uncategorized_recent">最近未分类</el-radio-button>
        <el-radio-button v-if="billIds.length" label="selected_bills">已选账单（{{ billIds.length }}）</el-radio-button>
      </el-radio-group>
      <el-input
        v-if="sampleMode === 'manual'"
        v-model="manualText"
        type="textarea"
        :rows="4"
        placeholder="每行一条样本，例如：星巴克 咖啡 微信支付 32.5"
        class="sample-input"
      />
      <el-alert
        v-else-if="sampleMode === 'selected_bills'"
        type="info"
        :closable="false"
        show-icon
        class="sample-alert"
        :title="`将使用已选中的 ${billIds.length} 条账单作为样本，仅生成规则建议，不会修改这些账单。`"
      />
      <div class="panel-actions">
        <el-button type="primary" size="small" :loading="generating" @click="handleGenerate">生成建议</el-button>
      </div>
    </div>

    <div v-if="currentSuggestion" class="suggestion-box">
      <div class="suggestion-summary">
        <strong>{{ currentSuggestion.summary || 'AI 建议' }}</strong>
        <span>建议 ID：{{ currentSuggestion.suggestion_id }}</span>
      </div>
      <el-table :data="suggestionRows" size="small" empty-text="暂无建议">
        <el-table-column width="48">
          <template #default="{ row }">
            <el-checkbox v-model="row._selected" :disabled="row.duplicate" />
          </template>
        </el-table-column>
        <el-table-column prop="keyword" label="关键词" min-width="110" />
        <el-table-column label="字段" min-width="110">
          <template #default="{ row }">{{ matchFieldLabel(row.match_field) }}</template>
        </el-table-column>
        <el-table-column prop="weight" label="权重" width="80" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">{{ Math.round((row.confidence || 0) * 100) }}%</template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.duplicate" size="small" type="info">已存在</el-tag>
            <el-popover v-else-if="row.conflict_level === 'cross_category'" placement="top" width="240" trigger="hover">
              <template #reference><el-tag size="small" type="warning">跨分类</el-tag></template>
              <div class="conflict-detail">
                <strong>已存在于其他分类：</strong>
                <div v-for="conflict in row.conflict_categories || []" :key="`${conflict.category_id}-${conflict.match_field}`">
                  {{ conflict.category_name }}（{{ matchFieldLabel(conflict.match_field) }}）
                </div>
              </div>
            </el-popover>
            <el-tag v-else size="small" type="success">可应用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="理由" min-width="180" show-overflow-tooltip />
      </el-table>
      <div class="panel-actions">
        <el-button v-if="currentSuggestion.isDraft !== false" type="primary" size="small" :loading="applying" @click="handleApply">应用选中</el-button>
        <el-button v-if="currentSuggestion.isDraft !== false" size="small" :loading="rejecting" @click="handleReject">拒绝建议</el-button>
      </div>
    </div>

    <div class="history-box">
      <div class="history-head">
        <div class="section-title">历史建议</div>
        <el-select v-model="historyStatus" size="small" class="history-filter" @change="loadHistory">
          <el-option label="全部状态" value="" />
          <el-option label="待审核" value="draft" />
          <el-option label="已应用" value="applied" />
          <el-option label="已拒绝" value="rejected" />
        </el-select>
      </div>
      <el-table :data="history" size="small" empty-text="暂无历史建议">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="category_name" label="分类" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag size="small" :type="statusTag(row.status)">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="摘要" min-width="180">
          <template #default="{ row }">{{ row.suggestion?.summary || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="row.status === 'draft'" link type="primary" size="small" @click="loadDraft(row)">载入审核</el-button>
            <el-button v-else link type="info" size="small" @click="viewHistory(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const props = defineProps({
  categoryId: { type: Number, required: true },
  categoryName: { type: String, default: '' },
  billIds: { type: Array, default: () => [] },
  initialSampleMode: { type: String, default: 'manual' },
})
const emit = defineEmits(['applied'])
const systemStore = useSystemStore()

const sampleMode = ref(props.initialSampleMode)
const manualText = ref('')
const generating = ref(false)
const applying = ref(false)
const rejecting = ref(false)
const currentSuggestion = ref(null)
const suggestionRows = ref([])
const history = ref([])
const historyStatus = ref('')

const matchFields = computed(() => systemStore.categoryMatchFields || [])

onMounted(async () => {
  if (!systemStore.categoryMatchFields.length) {
    await systemStore.loadCategoryMatchFields()
  }
  await loadHistory()
})
watch(() => props.categoryId, () => {
  currentSuggestion.value = null
  suggestionRows.value = []
  loadHistory()
})
watch(() => props.billIds.length, (count) => {
  if (!count && sampleMode.value === 'selected_bills') sampleMode.value = 'manual'
})

function parseManualSamples() {
  return manualText.value.split('\n').map(line => line.trim()).filter(Boolean).map(line => ({
    counterparty: line, product_desc: line, remark: '', direction: 'expense', amount_cents: 0, channel: 'manual_sample',
  }))
}

async function handleGenerate() {
  const manualSamples = sampleMode.value === 'manual' ? parseManualSamples() : []
  if (sampleMode.value === 'manual' && !manualSamples.length) return ElMessage.error('请输入至少一条样本')
  if (sampleMode.value === 'selected_bills' && !props.billIds.length) return ElMessage.error('请选择账单样本')
  generating.value = true
  try {
    const result = await systemStore.generateCategoryRuleSuggestion({
      category_id: props.categoryId,
      sample_mode: sampleMode.value,
      manual_samples: manualSamples,
      bill_ids: sampleMode.value === 'selected_bills' ? props.billIds : [],
      limit: 20,
    })
    setCurrentSuggestion(result, true)
    ElMessage.success('AI 建议已生成')
    await loadHistory()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    generating.value = false
  }
}

function setCurrentSuggestion(data, isDraft) {
  currentSuggestion.value = { ...data, isDraft }
  suggestionRows.value = (data.suggestions || []).map(item => ({
    ...item,
    _selected: isDraft && !item.duplicate && item.conflict_level === 'none' && (item.confidence || 0) >= 0.7,
  }))
}

async function handleApply() {
  const selected = suggestionRows.value.filter(row => row._selected)
  if (!currentSuggestion.value?.suggestion_id || !selected.length) return ElMessage.error('请选择要应用的建议')
  const conflictRows = selected.filter(row => row.conflict_level === 'cross_category')
  try {
    await ElMessageBox.confirm(`确定将 ${selected.length} 条建议写入“${props.categoryName}”吗？`, '应用 AI 建议', { type: 'warning' })
    if (conflictRows.length) {
      await ElMessageBox.confirm(
        `其中 ${conflictRows.length} 条关键词已存在于其他分类。继续应用可能影响后续自动分类，是否确认？`,
        '跨分类冲突确认',
        { type: 'warning', confirmButtonText: '仍然应用', cancelButtonText: '取消' },
      )
    }
  } catch {
    return
  }
  applying.value = true
  try {
    const result = await systemStore.approveCategoryRuleSuggestion(
      currentSuggestion.value.suggestion_id,
      selected.map(({ keyword, match_field, weight, priority }) => ({ keyword, match_field, weight, priority })),
      '',
      { allowCrossCategoryConflicts: conflictRows.length > 0 },
    )
    ElMessage.success(`已应用 ${result.inserted_count} 条建议`)
    currentSuggestion.value = null
    suggestionRows.value = []
    emit('applied')
    await loadHistory()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    applying.value = false
  }
}

async function handleReject() {
  if (!currentSuggestion.value?.suggestion_id) return
  rejecting.value = true
  try {
    await systemStore.rejectCategoryRuleSuggestion(currentSuggestion.value.suggestion_id)
    ElMessage.success('已拒绝该建议')
    currentSuggestion.value = null
    suggestionRows.value = []
    await loadHistory()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    rejecting.value = false
  }
}

async function loadHistory() {
  try {
    const data = await systemStore.listCategoryRuleSuggestions({ category_id: props.categoryId, status: historyStatus.value || undefined, limit: 20 })
    history.value = data.list || []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function loadDraft(row) {
  setCurrentSuggestion({
    suggestion_id: row.id,
    category: { id: row.target_category_id, name: row.category_name },
    summary: row.suggestion?.summary,
    suggestions: row.suggestion?.items || [],
  }, true)
}

function viewHistory(row) {
  setCurrentSuggestion({
    suggestion_id: row.id,
    category: { id: row.target_category_id, name: row.category_name },
    summary: row.suggestion?.summary,
    suggestions: row.suggestion?.items || [],
  }, false)
}

function matchFieldLabel(field) {
  return matchFields.value.find(f => f.field_key === field)?.label || field
}

function statusTag(status) {
  if (status === 'applied') return 'success'
  if (status === 'rejected') return 'info'
  if (status === 'draft') return 'warning'
  return 'info'
}
</script>

<style scoped>
.ai-category-panel { padding: var(--spacing-md); border: 1px solid var(--border-color-lighter); border-radius: var(--radius-lg); background: var(--bg-card-subtle); margin-bottom: var(--spacing-md); }
.panel-head, .panel-actions, .suggestion-summary, .history-head { display: flex; justify-content: space-between; align-items: center; gap: var(--spacing-md); flex-wrap: wrap; }
.sample-box, .suggestion-box, .history-box { margin-top: var(--spacing-md); }
.sample-input, .sample-alert { margin-top: var(--spacing-sm); }
.panel-actions { justify-content: flex-end; margin-top: var(--spacing-sm); }
.suggestion-summary { color: var(--color-text-secondary); font-size: var(--font-size-small); margin-bottom: var(--spacing-sm); }
.suggestion-summary strong { color: var(--color-text-primary); }
.history-filter { width: 140px; }
.conflict-detail { color: var(--color-text-regular); font-size: var(--font-size-small); line-height: 1.7; }
</style>
