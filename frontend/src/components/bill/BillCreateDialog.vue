<template>
  <el-dialog
    v-model="visible"
    title="手工记账"
    width="620px"
    append-to-body
    @open="loadOptions"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
      <el-form-item label="交易时间" prop="trade_time">
        <el-date-picker
          v-model="form.trade_time"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss+08:00"
          placeholder="选择交易时间"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="收支方向" prop="direction">
        <el-radio-group v-model="form.direction">
          <el-radio-button label="expense">支出</el-radio-button>
          <el-radio-button label="income">收入</el-radio-button>
          <el-radio-button label="neutral">中性</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="交易类型" prop="trade_type">
        <el-select v-model="form.trade_type" placeholder="选择交易类型" style="width: 100%">
          <el-option
            v-for="option in tradeTypeSelectOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="金额" prop="amount_yuan">
        <el-input-number
          v-model="form.amount_yuan"
          :precision="2"
          :min="0.01"
          :step="1"
          controls-position="right"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="账户">
        <el-select v-model="form.account_id" clearable filterable placeholder="选择账户" style="width: 100%">
          <el-option
            v-for="account in accounts"
            :key="account.id"
            :label="`${account.account_name}（${channelLabel(account.channel)}）`"
            :value="account.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="分类">
        <el-select v-model="form.category_id" clearable filterable placeholder="选择分类" style="width: 100%">
          <el-option
            v-for="category in categories"
            :key="category.id"
            :label="category.name"
            :value="category.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="交易对方">
        <el-input v-model="form.counterparty" placeholder="例如：商户、付款方" />
      </el-form-item>

      <el-form-item label="商品说明">
        <el-input v-model="form.product_desc" placeholder="例如：餐饮、交通、工资" />
      </el-form-item>

      <el-form-item label="支付方式">
        <el-input v-model="form.payment_method" placeholder="例如：现金、银行卡、余额" />
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { channelLabel, tradeTypeSelectOptions } from '@/utils/formatters'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'created'])

const visible = computed({
  get: () => props.modelValue,
  set: val => emit('update:modelValue', val),
})

const systemStore = useSystemStore()
const formRef = ref(null)
const submitting = ref(false)
const accounts = ref([])
const categories = ref([])

const form = reactive(defaultForm())

const rules = {
  trade_time: [{ required: true, message: '请选择交易时间', trigger: 'change' }],
  direction: [{ required: true, message: '请选择收支方向', trigger: 'change' }],
  trade_type: [{ required: true, message: '请选择交易类型', trigger: 'change' }],
  amount_yuan: [{ required: true, message: '请输入金额', trigger: 'blur' }],
}

function defaultForm() {
  return {
    trade_time: '',
    direction: 'expense',
    trade_type: 'consumption',
    amount_yuan: 0.01,
    account_id: null,
    category_id: null,
    counterparty: '',
    product_desc: '',
    payment_method: '',
    remark: '',
  }
}

async function loadOptions() {
  await Promise.all([
    systemStore.loadAccounts(null),
    systemStore.loadCategories(),
  ])
  accounts.value = systemStore.accounts
  categories.value = systemStore.categories
}

function resetForm() {
  Object.assign(form, defaultForm())
  formRef.value?.clearValidate()
}

watch(visible, (val) => {
  if (!val) resetForm()
})

async function submit() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const fields = {
      trade_time: form.trade_time,
      direction: form.direction,
      trade_type: form.trade_type,
      amount_cents: Math.round(Number(form.amount_yuan || 0) * 100),
      account_id: form.account_id,
      category_id: form.category_id,
      counterparty: form.counterparty,
      product_desc: form.product_desc,
      payment_method: form.payment_method,
      remark: form.remark,
      status: '手工录入',
    }
    emit('created', fields)
    resetForm()
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
</script>
