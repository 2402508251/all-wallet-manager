<template>
  <div class="page-container">
    <h2 class="page-title">账单管理</h2>

    <!-- 筛选条件 -->
    <BillFilter @search="handleSearch" @reset="handleReset" />

    <!-- 账单表格 -->
    <BillTable
      :bills="billStore.bills"
      :total="billStore.total"
      :loading="billStore.loading"
      @row-click="handleRowClick"
      @batch-delete="handleBatchDelete"
    />

    <!-- 账单详情抽屉 -->
    <BillDetailDrawer
      :bill-id="selectedBillId"
      @close="selectedBillId = null"
      @update="onDetailUpdated"
      @delete="onDetailDeleted"
    />

    <!-- 回收站入口 -->
    <div class="recycle-bin-entry">
      <el-button size="small" @click="showRecycleBin = true">
        <el-icon><Delete /></el-icon>
        回收站
      </el-button>
    </div>

    <!-- 回收站弹窗 -->
    <el-dialog v-model="showRecycleBin" title="回收站" width="900px" append-to-body>
      <el-table v-loading="recycleLoading" :data="deletedBills" size="small" empty-text="回收站为空">
        <el-table-column prop="trade_time" label="交易时间" width="140">
          <template #default="{ row }">{{ row.trade_time?.slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column prop="counterparty" label="交易对方" min-width="120" show-overflow-tooltip />
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
      <div style="margin-top: 12px; display: flex; justify-content: space-between">
        <el-button size="small" type="danger" @click="handleEmptyRecycleBin">清空回收站</el-button>
        <el-button size="small" @click="showRecycleBin = false">关闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useBillStore } from '@/stores/bill'
import BillFilter from '@/components/bill/BillFilter.vue'
import BillTable from '@/components/bill/BillTable.vue'
import BillDetailDrawer from '@/components/bill/BillDetailDrawer.vue'

const billStore = useBillStore()
const route = useRoute()
const selectedBillId = ref(null)
const showRecycleBin = ref(false)
const deletedBills = ref([])
const recycleLoading = ref(false)

onMounted(() => {
  if (Object.keys(route.query).length > 0) {
    billStore.applyQueryFilter(route.query)
  }
  billStore.queryBills()
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

async function handleBatchDelete(ids) {
  try {
    await billStore.deleteBills(ids)
    ElMessage.success(`已删除 ${ids.length} 条账单（移入回收站）`)
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
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
.recycle-bin-entry {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 10;
}
</style>