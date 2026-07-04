<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑信用账户' : '新建信用账户'"
    width="450px"
    :close-on-click-modal="false"
  >
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item label="账户名称" required>
        <el-input v-model="form.account_name" placeholder="如 花呗、京东白条" />
      </el-form-item>
      <el-form-item label="信用类型" required>
        <el-select v-model="form.credit_type" placeholder="选择类型">
          <el-option label="花呗" value="huabei" />
          <el-option label="京东白条" value="baitiao" />
          <el-option label="微信分付" value="fenfu" />
          <el-option label="建行信用卡" value="ccb_credit" />
        </el-select>
      </el-form-item>
      <el-form-item label="信用额度">
        <el-input-number v-model="creditLimitYuan" :min="0" :step="100" placeholder="0" />
        <span style="margin-left:8px;color:#909399">元</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountingStore } from '@/stores/accounting'

const emit = defineEmits(['success'])

const accountingStore = useAccountingStore()

const visible = ref(false)
const formRef = ref(null)
const isEdit = ref(false)
const editId = ref(null)
const saving = ref(false)

const form = reactive({
  account_name: '',
  credit_type: '',
  credit_limit_cents: 0,
})

const creditLimitYuan = computed({
  get: () => form.credit_limit_cents / 100,
  set: (val) => { form.credit_limit_cents = Math.round(val * 100) },
})

function open(account) {
  if (account) {
    isEdit.value = true
    editId.value = account.id
    form.account_name = account.account_name
    form.credit_type = account.credit_type
    form.credit_limit_cents = account.credit_limit_cents || 0
  } else {
    isEdit.value = false
    editId.value = null
    form.account_name = ''
    form.credit_type = ''
    form.credit_limit_cents = 0
  }
  visible.value = true
}

async function handleSave() {
  if (!form.account_name || !form.credit_type) {
    ElMessage.warning('请填写账户名称和信用类型')
    return
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await accountingStore.updateCreditAccount(editId.value, { ...form })
    } else {
      // 信用账户创建暂时通过 updateAccount 处理
      await accountingStore.updateCreditAccount(editId.value, { ...form })
    }
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    visible.value = false
    emit('success')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>
