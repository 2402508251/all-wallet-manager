<template>
  <div class="card-box">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px">
      <template #title>
        重新分类将使用最新分类规则，对账单自身与发起方文本重新打分。支出未命中时将归入“其他支出(未命中)”，收入默认归入“收入”。执行前会创建快照，不会覆盖手工分类。
      </template>
    </el-alert>

    <div class="recategorize-form">
      <div class="form-row">
        <span class="form-label">分类范围：</span>
        <el-radio-group v-model="scope.type">
          <el-radio value="all">全部</el-radio>
          <el-radio value="channel">按渠道</el-radio>
          <el-radio value="time_range">按时间</el-radio>
          <el-radio value="bill_ids">按账单ID</el-radio>
        </el-radio-group>
      </div>

      <div class="form-row" v-if="scope.type === 'channel'">
        <span class="form-label">渠道：</span>
        <el-select v-model="scope.channel" placeholder="选择渠道">
          <el-option label="微信" value="wechat" />
          <el-option label="支付宝" value="alipay" />
          <el-option label="建行" value="ccb" />
        </el-select>
      </div>

      <div class="form-row" v-if="scope.type === 'time_range'">
        <span class="form-label">起止时间：</span>
        <el-date-picker
          v-model="timeRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
        />
      </div>

      <div class="form-row" v-if="scope.type === 'bill_ids'">
        <span class="form-label">账单ID：</span>
        <el-input
          v-model="scope.bill_ids_text"
          type="textarea"
          placeholder="输入账单ID，多个ID用逗号分隔"
          :rows="2"
          style="flex: 1"
        />
      </div>

      <div class="form-row">
        <span class="form-label">选项：</span>
        <el-checkbox v-model="onlyUncategorized">仅处理未命中</el-checkbox>
        <el-checkbox v-model="includeIncome">纳入历史收入账单</el-checkbox>
      </div>

      <div class="form-row">
        <el-button type="primary" :loading="running" @click="handleRecategorize">
          开始重新分类
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const emit = defineEmits(['done'])
const systemStore = useSystemStore()
const running = ref(false)
const timeRange = ref(null)
const onlyUncategorized = ref(false)
const includeIncome = ref(false)

const scope = reactive({
  type: 'all',
  channel: null,
  bill_ids_text: '',
})

function buildScope() {
  const params = { type: scope.type }
  if (scope.type === 'channel') params.channel = scope.channel
  if (scope.type === 'time_range' && timeRange.value?.length === 2) {
    params.start_time = timeRange.value[0]
    params.end_time = timeRange.value[1]
  }
  if (scope.type === 'bill_ids' && scope.bill_ids_text.trim()) {
    params.bill_ids = scope.bill_ids_text
      .split(/[,，\s]+/)
      .map(s => s.trim())
      .filter(s => s)
      .map(Number)
      .filter(n => !isNaN(n))
  }
  return params
}

async function handleRecategorize() {
  try {
    await ElMessageBox.confirm(
      '确定要重新分类吗？此操作会创建快照备份，且不会覆盖手工分类。',
      '确认重新分类',
      { type: 'info' }
    )
  } catch { return }

  running.value = true
  try {
    const data = await systemStore.recategorizeBills(buildScope(), {
      only_uncategorized: onlyUncategorized.value,
      include_income: includeIncome.value,
    })
    ElMessage.success(`重新分类完成：扫描 ${data.scanned}，更新 ${data.updated}，跳过手工 ${data.skipped_manual}`)
    emit('done')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.recategorize-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.form-label {
  min-width: 80px;
  color: var(--color-text-secondary);
}
</style>
