<template>
  <div class="card-box">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px">
      <template #title>
        重新解析将基于源账单数据，使用最新的分类关键词和枚举映射配置重新处理。
        重新解析前将自动创建快照备份。
      </template>
    </el-alert>

    <div class="reparse-form">
      <div class="form-row">
        <span class="form-label">解析范围：</span>
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
        <el-button type="primary" :loading="running" @click="handleReparse">
          开始重新解析
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

const scope = reactive({
  type: 'all',
  channel: null,
  start_time: null,
  end_time: null,
  bill_ids_text: '',
})

async function handleReparse() {
  try {
    await ElMessageBox.confirm(
      '确定要重新解析吗？此操作会创建快照备份，解析后可按需回退。',
      '确认重新解析',
      { type: 'info' }
    )
  } catch { return }

  running.value = true
  try {
    const params = { type: scope.type }
    if (scope.type === 'channel') {
      params.channel = scope.channel
    }
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

    const data = await systemStore.reparse(params)
    ElMessage.success(`重新解析完成${data ? '' : ''}`)
    emit('done')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.reparse-form {
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