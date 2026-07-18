<template>
  <div class="page-container">
    <section class="page-hero">
      <div>
        <div class="page-kicker">Bills</div>
        <h2 class="page-title">账单管理</h2>
        <p class="page-subtitle">查询、编辑、批量维护账单，并通过回收站恢复误删数据。</p>
      </div>
      <el-button @click="showRecycleBin = true">
        <el-icon><Delete /></el-icon>
        回收站
      </el-button>
    </section>

    <BillFilter :filter="billStore.filter" @search="handleSearch" @reset="handleReset" />

    <div class="bill-summary card-box">
      <div>
        <div class="section-subtitle">当前条件汇总</div>
        <div class="bill-summary-total">共 {{ billStore.total }} 条</div>
      </div>
      <div class="bill-summary-metrics">
        <div class="bill-summary-item">
          <span>总收入</span>
          <strong class="amount-income">{{ formatYuan(billStore.summary.income) }}</strong>
        </div>
        <div class="bill-summary-item">
          <span>总支出</span>
          <strong class="amount-expense">{{ formatYuan(billStore.summary.expense) }}</strong>
        </div>
      </div>
    </div>

    <BillTable
      :bills="billStore.bills"
      :total="billStore.total"
      :loading="billStore.loading"
      @row-click="handleRowClick"
      @batch-delete="handleBatchDelete"
      @selection-change="handleBillSelectionChange"
      @generate-category-suggestions="openAiSuggestionDialog"
      @create="showCreateDialog = true"
    />

    <BillCreateDialog
      v-model="showCreateDialog"
      @created="handleCreateBill"
    />

    <BillDetailDrawer
      :bill-id="selectedBillId"
      @close="selectedBillId = null"
      @update="onDetailUpdated"
      @delete="onDetailDeleted"
    />

    <el-dialog v-model="showAiSuggestionDialog" title="从选中账单生成分类关键词" width="920px" append-to-body>
      <div v-if="!showAiSuggestionPanel" class="ai-category-picker">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          :title="`已选 ${selectedBillIds.length} 条账单。此操作仅生成分类关键词建议，不会修改已选账单。`"
        />
        <el-form label-width="90px" class="ai-category-form">
          <el-form-item label="目标分类">
            <el-select v-model="aiSuggestionCategoryId" placeholder="选择要生成规则的分类" style="width:100%">
              <el-option v-for="category in enabledCategories" :key="category.id" :label="category.name" :value="category.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="ai-dialog-actions">
          <el-button @click="showAiSuggestionDialog = false">取消</el-button>
          <el-button type="primary" :disabled="!aiSuggestionCategoryId" @click="startAiSuggestionReview">开始审核</el-button>
        </div>
      </div>
      <AiCategorySuggestionPanel
        v-else
        :category-id="aiSuggestionCategoryId"
        :category-name="aiSuggestionCategoryName"
        :bill-ids="selectedBillIds"
        initial-sample-mode="selected_bills"
        @applied="handleAiSuggestionApplied"
      />
    </el-dialog>

    <el-dialog v-model="showRecycleBin" title="回收站" width="900px" append-to-body>
      <el-table v-loading="recycleLoading" :data="deletedBills" size="small" empty-text="回收站为空">
        <el-table-column prop="trade_time" label="交易时间" width="140">
          <template #default="{ row }">{{ row.trade_time?.slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column prop="product_desc" label="商品说明" min-width="120" show-overflow-tooltip />
        <el-table-column label="金额" width="100" align="right">
          <template #default="{ row }">¥{{ (row.amount_cents / 100).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleRestore(row)">恢复</el-button>
            <el-button link type="danger" size="small" @click="handlePermanentDelete(row)">永久删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="recycle-footer">
        <el-button size="small" type="danger" @click="handleEmptyRecycleBin">清空回收站</el-button>
        <el-button size="small" @click="showRecycleBin = false">关闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useBillStore } from '@/stores/bill'
import { useSystemStore } from '@/stores/system'
import BillFilter from '@/components/bill/BillFilter.vue'
import BillTable from '@/components/bill/BillTable.vue'
import BillCreateDialog from '@/components/bill/BillCreateDialog.vue'
import BillDetailDrawer from '@/components/bill/BillDetailDrawer.vue'
import AiCategorySuggestionPanel from '@/components/settings/AiCategorySuggestionPanel.vue'
import { formatYuan } from '@/utils/formatters'

const billStore = useBillStore()
const systemStore = useSystemStore()
const route = useRoute()
const selectedBillId = ref(null)
const selectedBillIds = ref([])
const selectedBillRows = ref([])
const showAiSuggestionDialog = ref(false)
const showAiSuggestionPanel = ref(false)
const aiSuggestionCategoryId = ref(null)
const enabledCategories = computed(() => systemStore.categories.filter(category => category.is_enabled !== 0))
const aiSuggestionCategoryName = computed(() => {
  const category = systemStore.categories.find(item => item.id === aiSuggestionCategoryId.value)
  return category?.name || ''
})
const showCreateDialog = ref(false)
const showRecycleBin = ref(false)
const deletedBills = ref([])
const recycleLoading = ref(false)

onMounted(async () => {
  if (Object.keys(route.query).length > 0) {
    billStore.applyQueryFilter(route.query)
  }
  billStore.queryBills()
  if (!systemStore.categories.length) await systemStore.loadCategories()
  if (route.query.recycle === '1') {
    showRecycleBin.value = true
  }
})

function handleSearch(filter) {
  billStore.setFilter(filter)
  billStore.page = 1
  billStore.queryBills()
}

function handleReset() {
  billStore.resetFilter()
  billStore.queryBills()
}

function handleRowClick(row) {
  selectedBillId.value = row.id
}

function handleBillSelectionChange(payload) {
  selectedBillIds.value = payload.ids || []
  selectedBillRows.value = payload.rows || []
}

function openAiSuggestionDialog(payload) {
  selectedBillIds.value = payload.ids || selectedBillIds.value
  selectedBillRows.value = payload.rows || selectedBillRows.value
  if (!selectedBillIds.value.length) {
    ElMessage.error('请选择账单样本')
    return
  }
  aiSuggestionCategoryId.value = null
  showAiSuggestionPanel.value = false
  showAiSuggestionDialog.value = true
}

function startAiSuggestionReview() {
  if (!aiSuggestionCategoryId.value) {
    ElMessage.error('请选择目标分类')
    return
  }
  showAiSuggestionPanel.value = true
}

function handleAiSuggestionApplied() {
  ElMessage.success('AI 分类关键词已应用；已选账单不会被自动修改')
  showAiSuggestionDialog.value = false
  showAiSuggestionPanel.value = false
}

async function handleBatchDelete(ids) {
  try {
    await billStore.deleteBills(ids)
    ElMessage.success(`已删除 ${ids.length} 条账单（移入回收站）`)
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function handleCreateBill(fields) {
  try {
    const data = await billStore.createBill(fields)
    showCreateDialog.value = false
    selectedBillId.value = data.bill_id
    ElMessage.success('手工账单已新增')
  } catch (e) {
    ElMessage.error(e.message || '新增失败')
  }
}

function onDetailUpdated() {
  billStore.queryBills()
}

function onDetailDeleted() {
  selectedBillId.value = null
  billStore.queryBills()
  ElMessage.success('账单已移入回收站')
}

async function loadDeletedBills() {
  recycleLoading.value = true
  try {
    const data = await billStore.getDeletedBills()
    deletedBills.value = data.list || []
  } catch {
    deletedBills.value = []
  } finally {
    recycleLoading.value = false
  }
}

async function handleRestore(row) {
  try {
    await billStore.restoreBill(row.id)
    ElMessage.success('账单已恢复')
    await loadDeletedBills()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handlePermanentDelete(row) {
  try {
    await ElMessageBox.confirm('永久删除不可恢复，确定继续？', '确认', { type: 'warning' })
    await billStore.permanentDeleteBill(row.id)
    ElMessage.success('已永久删除')
    await loadDeletedBills()
  } catch { /* 取消 */ }
}

async function handleEmptyRecycleBin() {
  try {
    await ElMessageBox.confirm('将永久删除回收站中所有账单，不可恢复！', '确认清空', { type: 'warning' })
    await billStore.emptyRecycleBin()
    ElMessage.success('回收站已清空')
    await loadDeletedBills()
  } catch { /* 取消 */ }
}

watch(showRecycleBin, (val) => {
  if (val) loadDeletedBills()
})
</script>

<style scoped>
.ai-category-picker {
  display: grid;
  gap: var(--spacing-md);
}

.ai-category-form {
  margin-top: var(--spacing-sm);
}

.ai-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

.recycle-footer {
  display: flex;
  justify-content: space-between;
  margin-top: var(--spacing-md);
}

.bill-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.bill-summary-total {
  margin-top: 2px;
  color: var(--color-text-primary);
  font-weight: 700;
}

.bill-summary-metrics {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

.bill-summary-item {
  display: grid;
  gap: 2px;
  text-align: right;
}

.bill-summary-item span {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.bill-summary-item strong {
  font-size: var(--font-size-large);
}

@media (max-width: 768px) {
  .bill-summary {
    align-items: flex-start;
    flex-direction: column;
  }

  .bill-summary-item {
    text-align: left;
  }
}
</style>
