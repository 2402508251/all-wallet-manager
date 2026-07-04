<template>
  <el-drawer
    v-model="visible"
    title="账单详情"
    :size="500"
    direction="rtl"
    @close="handleClose"
  >
    <el-tabs v-model="activeTab" v-loading="loading">
      <el-tab-pane label="基础信息" name="basic">
        <BillBasicInfo
          :bill="bill"
          @update="handleUpdate"
          @delete="handleDelete"
        />
      </el-tab-pane>
      <el-tab-pane label="源账单" name="source">
        <BillSourceInfo :source-bill="sourceBill" />
      </el-tab-pane>
      <el-tab-pane label="账务状态" name="accounting">
        <BillAccountingInfo :bill="bill" />
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useBillStore } from '@/stores/bill'
import { useSystemStore } from '@/stores/system'
import BillBasicInfo from './BillBasicInfo.vue'
import BillSourceInfo from './BillSourceInfo.vue'
import BillAccountingInfo from './BillAccountingInfo.vue'

const props = defineProps({
  billId: { type: Number, default: null },
})

const emit = defineEmits(['close', 'update', 'delete'])

const billStore = useBillStore()
const systemStore = useSystemStore()

const visible = ref(false)
const activeTab = ref('basic')
const bill = ref(null)
const sourceBill = ref(null)
const loading = ref(false)

watch(() => props.billId, async (id) => {
  if (id) {
    visible.value = true
    loading.value = true
    try {
      await Promise.all([
        systemStore.loadFamilies(),
        systemStore.loadCategories(),
        billStore.getBillDetail(id),
      ]).then(results => {
        bill.value = results[2]
        sourceBill.value = results[2]?.source_bill || null
      })
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })

function handleClose() {
  visible.value = false
  activeTab.value = 'basic'
  emit('close')
}

async function handleUpdate(fields) {
  if (props.billId) {
    await billStore.updateBill(props.billId, fields)
    emit('update', fields)
    // 刷新详情
    const data = await billStore.getBillDetail(props.billId)
    bill.value = data
  }
}

async function handleDelete() {
  if (props.billId) {
    await billStore.deleteBill(props.billId)
    visible.value = false
    emit('delete')
  }
}
</script>