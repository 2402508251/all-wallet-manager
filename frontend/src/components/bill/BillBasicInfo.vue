<template>
  <div v-if="bill" class="bill-info">
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="交易时间">
        {{ formatTime(bill.trade_time) }}
      </el-descriptions-item>
      <el-descriptions-item label="交易类型">
        <el-tag size="small">{{ tradeTypeLabel(bill.trade_type) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="交易对方">
        {{ bill.counterparty || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="金额">
        <strong :class="directionClass(bill.direction)">
          {{ formatAmount(bill.amount_cents, bill.direction) }}
        </strong>
      </el-descriptions-item>
      <el-descriptions-item label="商品说明">
        {{ bill.product_desc || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="支付方式">
        {{ bill.payment_method || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="交易状态">
        {{ bill.status || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="所属账户">
        {{ accountName }}
      </el-descriptions-item>
      <el-descriptions-item label="所属角色">
        {{ roleName }}
      </el-descriptions-item>
      <el-descriptions-item label="所属家庭">
        <div style="display: flex; align-items: center; gap: 8px">
          <span>{{ familyName }}</span>
          <el-button
            v-if="canReassignFamily"
            link type="primary" size="small"
            @click="showFamilyReassign = true"
          >变更</el-button>
        </div>
      </el-descriptions-item>
      <el-descriptions-item label="渠道交易单号">
        <span style="font-size:12px;word-break:break-all">{{ bill.channel_trade_no }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="备注">
        {{ bill.remark || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="业务分类">
        <el-select
          :model-value="bill.category_id"
          size="small"
          clearable
          placeholder="选择分类"
          @change="handleCategoryChange"
        >
          <el-option
            v-for="c in categories"
            :key="c.id"
            :label="c.name"
            :value="c.id"
          />
        </el-select>
      </el-descriptions-item>
    </el-descriptions>

    <el-dialog v-model="showFamilyReassign" title="变更归属家庭" width="400px" append-to-body>
      <p style="margin-bottom: 12px; color: var(--color-text-secondary)">
        此角色关联了多个家庭，可选择将此账单归属到哪个家庭。
      </p>
      <el-select v-model="targetFamilyId" placeholder="选择目标家庭" style="width: 100%">
        <el-option
          v-for="rf in roleFamilies"
          :key="rf.family_id"
          :label="rf.family_name || `家庭#${rf.family_id}`"
          :value="rf.family_id"
        />
      </el-select>
      <template #footer>
        <el-button @click="showFamilyReassign = false">取消</el-button>
        <el-button type="primary" :disabled="!targetFamilyId" @click="handleReassignFamily">确认变更</el-button>
      </template>
    </el-dialog>

    <div class="bill-actions">
      <el-button type="danger" size="small" @click="handleDelete">
        <el-icon><Delete /></el-icon>
        删除此账单
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useSystemStore } from '@/stores/system'
import { useBillStore } from '@/stores/bill'

const props = defineProps({
  bill: { type: Object, default: null },
})

const emit = defineEmits(['update', 'delete'])

const systemStore = useSystemStore()
const billStore = useBillStore()

const categories = computed(() => systemStore.categories)
const showFamilyReassign = ref(false)
const targetFamilyId = ref(null)
const roleFamilies = ref([])

const accountName = computed(() => {
  if (!props.bill?.account_id) return '-'
  const acc = systemStore.accounts.find(a => a.id === props.bill.account_id)
  return acc?.account_name || props.bill.account_id
})

const roleName = computed(() => {
  if (!props.bill?.role_id) return '-'
  const role = systemStore.roles.find(r => r.id === props.bill.role_id)
  return role?.name || `角色#${props.bill.role_id}`
})

const familyName = computed(() => {
  if (!props.bill?.family_id) return '-'
  const family = systemStore.families.find(f => f.id === props.bill.family_id)
  return family?.name || `家庭#${props.bill.family_id}`
})

const canReassignFamily = computed(() => {
  return props.bill?.role_id && roleFamilies.value.length > 1
})

watch(() => props.bill?.role_id, async (roleId) => {
  if (roleId) {
    try {
      roleFamilies.value = await systemStore.getRoleFamilies(roleId)
    } catch {
      roleFamilies.value = []
    }
  } else {
    roleFamilies.value = []
  }
}, { immediate: true })

function tradeTypeLabel(type) {
  const map = {
    consumption: '消费',
    refund: '退款',
    transfer_out: '转出',
    transfer_in: '转入',
    repayment: '还款',
    credit_consumption: '信用消费',
    fee: '手续费',
    mirror: '镜像',
    topup: '充值',
    withdrawal: '提现',
    investment: '理财',
    other: '其他',
  }
  return map[type] || type
}

function directionClass(dir) {
  const map = { income: 'amount-income', expense: 'amount-expense', neutral: 'amount-neutral' }
  return map[dir] || ''
}

function formatAmount(cents, direction) {
  const yuan = (cents / 100).toFixed(2)
  const prefix = direction === 'income' ? '+' : direction === 'expense' ? '-' : ''
  return `${prefix}¥${yuan}`
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr.slice(0, 19).replace('T', ' ')
}

function handleCategoryChange(categoryId) {
  emit('update', { category_id: categoryId })
  ElMessage.success('分类已更新')
}

async function handleReassignFamily() {
  if (!targetFamilyId.value) return
  try {
    await billStore.reassignBillFamily(props.bill.id, targetFamilyId.value)
    ElMessage.success('家庭已变更')
    showFamilyReassign.value = false
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function handleDelete() {
  ElMessageBox.confirm(
    '确定要删除此账单吗？此操作将移入回收站，可恢复。',
    '确认删除',
    { type: 'warning' }
  ).then(() => {
    emit('delete')
  }).catch(() => {})
}
</script>

<style scoped>
.bill-info {
  padding: var(--spacing-sm);
}

.bill-actions {
  margin-top: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}
</style>