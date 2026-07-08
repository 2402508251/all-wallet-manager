<template>
  <div class="card-box">
    <div class="action-bar">
      <div>
        <div class="section-title">账单列表</div>
        <div class="section-subtitle">
          共 {{ total }} 条<span v-if="selectedIds.length > 0">，已选 {{ selectedIds.length }} 条</span>
        </div>
      </div>
      <div class="table-actions">
        <el-button
          v-if="selectedIds.length > 0"
          type="primary"
          size="small"
          @click="handleBatchReassign"
        >
          批量改账户 ({{ selectedIds.length }})
        </el-button>
        <el-button
          v-if="selectedIds.length > 0"
          type="danger"
          size="small"
          @click="handleBatchDelete"
        >
          批量删除 ({{ selectedIds.length }})
        </el-button>
      </div>
    </div>

    <el-table
      v-loading="loading"
      :data="bills"
      style="width: 100%"
      size="default"
      empty-text="暂无账单数据"
      @selection-change="handleSelectionChange"
      @row-click="handleRowClick"
      highlight-current-row
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="trade_time" label="交易时间" width="150">
        <template #default="{ row }">
          {{ formatTime(row.trade_time) }}
        </template>
      </el-table-column>
      <el-table-column label="渠道" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="channelTag(row.channel)">
            {{ channelLabel(row.channel) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="product_desc" label="商品说明" min-width="130" show-overflow-tooltip />
      <el-table-column label="收支" width="65">
        <template #default="{ row }">
          <span :class="directionClass(row.direction)">
            {{ directionLabel(row.direction) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">
          <span :class="amountClass(row)">
            {{ formatAmount(row.amount_cents, row.direction) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag
            v-if="row.trade_type && row.trade_type !== 'consumption'"
            size="small"
            :type="tradeTypeTag(row.trade_type)"
          >
            {{ tradeTypeLabel(row.trade_type) }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="90">
        <template #default="{ row }">
          {{ row.category_name || getCategoryName(row.category_id) || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="角色" width="70" show-overflow-tooltip>
        <template #default="{ row }">
          {{ getRoleName(row.role_id) }}
        </template>
      </el-table-column>
    </el-table>

    <div class="table-footer">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="currentPageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        small
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <el-dialog v-model="reassignVisible" title="批量修改账户" width="450px">
      <p style="margin-bottom: 12px">
        将选中的 {{ selectedIds.length }} 条账单转移到新账户，同时重新派生角色和家庭。
      </p>
      <el-select v-model="reassignAccountId" placeholder="选择目标账户" style="width: 100%">
        <el-option
          v-for="a in allAccounts"
          :key="a.id"
          :label="`${a.account_name} (${channelLabel(a.channel)})`"
          :value="a.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="reassignVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!reassignAccountId" @click="confirmReassign">确认转移</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useBillStore } from '@/stores/bill'
import { useSystemStore } from '@/stores/system'
import {
  channelLabel as formatChannelLabel,
  channelTag as formatChannelTag,
  directionClass as formatDirectionClass,
  directionLabel as formatDirectionLabel,
  formatDateTime,
  formatSignedYuan,
  tradeTypeLabel as formatTradeTypeLabel,
  tradeTypeTag as formatTradeTypeTag,
} from '@/utils/formatters'

const props = defineProps({
  bills: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['row-click', 'batch-delete'])

const billStore = useBillStore()
const systemStore = useSystemStore()

const selectedIds = ref([])
const currentPage = ref(1)
const currentPageSize = ref(20)
const reassignVisible = ref(false)
const reassignAccountId = ref(null)
const allAccounts = ref([])

function handleSelectionChange(rows) {
  selectedIds.value = rows.map(r => r.id)
}

function handleRowClick(row) {
  emit('row-click', row)
}

function handleBatchDelete() {
  ElMessageBox.confirm(
    `确定要删除选中的 ${selectedIds.value.length} 条账单吗？将移入回收站，可恢复。`,
    '确认删除',
    { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  ).then(() => {
    emit('batch-delete', selectedIds.value)
    selectedIds.value = []
  }).catch(() => {})
}

async function handleBatchReassign() {
  await systemStore.loadAccounts(null)
  allAccounts.value = systemStore.accounts
  reassignAccountId.value = null
  reassignVisible.value = true
}

async function confirmReassign() {
  if (!reassignAccountId.value) return
  try {
    await billStore.batchReassignBills(selectedIds.value, reassignAccountId.value)
    ElMessage.success(`已转移 ${selectedIds.value.length} 条账单`)
    selectedIds.value = []
    reassignVisible.value = false
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function handlePageChange(page) {
  currentPage.value = page
  billStore.page = page
  billStore.queryBills()
}

function handleSizeChange(size) {
  currentPageSize.value = size
  billStore.pageSize = size
  billStore.page = 1
  billStore.queryBills()
}

function channelLabel(ch) {
  return formatChannelLabel(ch)
}

function channelTag(ch) {
  return formatChannelTag(ch)
}

function directionLabel(dir) {
  return formatDirectionLabel(dir)
}

function directionClass(dir) {
  return formatDirectionClass(dir)
}

function amountClass(row) {
  if (row.trade_type === 'credit_consumption') return 'amount-expense'
  if (row.is_system) return 'amount-neutral'
  return directionClass(row.direction)
}

function tradeTypeLabel(type) {
  return formatTradeTypeLabel(type)
}

function tradeTypeTag(type) {
  return formatTradeTypeTag(type)
}

function formatAmount(cents, direction) {
  return formatSignedYuan(cents, direction)
}

function formatTime(timeStr) {
  return formatDateTime(timeStr)
}

function getCategoryName(categoryId) {
  if (!categoryId) return null
  const cat = systemStore.categories.find(c => c.id === categoryId)
  return cat?.name || null
}

function getRoleName(roleId) {
  if (!roleId) return '-'
  const role = systemStore.roles.find(r => r.id === roleId)
  return role?.name || '-'
}
</script>

<style scoped>
.table-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  justify-content: flex-end;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--spacing-md);
}
</style>
