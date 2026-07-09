<template>
  <div class="ai-setting">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="ai-alert"
      title="Phase 0 仅提供 AI 配置、健康检查和任务记录骨架；AI 生成的业务建议会在后续阶段接入。"
    />

    <div class="section-title">Provider 配置</div>
    <div class="card-box ai-card">
      <el-form label-width="120px" size="small" :model="form">
        <el-form-item label="Provider 类型">
          <el-select v-model="form.provider_type" placeholder="选择 Provider">
            <el-option label="OpenAI 兼容接口" value="openai_compatible" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称" required>
          <el-input v-model="form.model_name" placeholder="例如 gpt-4o-mini / qwen-plus / deepseek-chat" />
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="form.api_base" placeholder="兼容接口地址，留空使用 SDK 默认地址" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            placeholder="留空则保留已保存密钥"
          />
          <div v-if="form.has_api_key" class="field-hint">已保存密钥：{{ form.api_key_masked || '****' }}</div>
        </el-form-item>
        <el-form-item label="Temperature">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="超时秒数">
          <el-input-number v-model="form.timeout_seconds" :min="5" :max="300" />
        </el-form-item>
        <el-form-item label="Max Tokens">
          <el-input-number v-model="form.max_tokens" :min="256" :max="32000" :step="256" />
        </el-form-item>
        <el-form-item label="启用任务">
          <el-checkbox-group v-model="form.enabled_tasks">
            <el-checkbox label="category_mapping">分类关键词建议</el-checkbox>
            <el-checkbox label="parser_rule">解析规则建议</el-checkbox>
            <el-checkbox label="report_generation">AI 报表助手</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" :active-value="1" :inactive-value="0" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
          <el-button :loading="testing" @click="handleTest">健康检查</el-button>
          <el-button :loading="mocking" @click="handleMockTask">创建测试任务</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="action-bar">
      <div>
        <div class="section-title">AI 任务记录</div>
        <div class="section-subtitle">用于确认 Phase 0 的任务落库、状态记录与错误追踪能力。</div>
      </div>
      <el-button size="small" @click="loadTasks">刷新</el-button>
    </div>
    <el-table :data="systemStore.aiTasks" size="small" empty-text="暂无 AI 任务记录">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="task_type" label="任务类型" min-width="140" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTag(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="provider" label="Provider" min-width="130" />
      <el-table-column prop="model_name" label="模型" min-width="160" />
      <el-table-column prop="error_message" label="错误" min-width="180" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="170" />
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const saving = ref(false)
const testing = ref(false)
const mocking = ref(false)

const form = reactive(defaultForm())

function defaultForm() {
  return {
    provider_type: 'openai_compatible',
    model_name: '',
    api_base: '',
    api_key: '',
    api_key_masked: '',
    has_api_key: false,
    temperature: 0.2,
    timeout_seconds: 60,
    max_tokens: 2048,
    enabled_tasks: ['category_mapping'],
    is_enabled: 1,
  }
}

onMounted(async () => {
  await loadConfig()
  await loadTasks()
})

async function loadConfig() {
  try {
    const config = await systemStore.loadAiConfig()
    Object.assign(form, defaultForm(), config, { api_key: '' })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadTasks() {
  try {
    await systemStore.loadAiTasks({ limit: 20 })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleSave() {
  saving.value = true
  try {
    const saved = await systemStore.saveAiConfig({ ...form })
    Object.assign(form, defaultForm(), saved, { api_key: '' })
    ElMessage.success('AI 配置已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  try {
    const result = await systemStore.testAiConnection()
    ElMessage.success(`连接成功：${result.model_name}`)
    await loadTasks()
  } catch (e) {
    ElMessage.error(e.message)
    await loadTasks()
  } finally {
    testing.value = false
  }
}

async function handleMockTask() {
  mocking.value = true
  try {
    await systemStore.createAiMockTask('phase0_mock')
    ElMessage.success('已创建测试任务')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    mocking.value = false
  }
}

function statusTag(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}
</script>

<style scoped>
.ai-alert {
  margin-bottom: var(--spacing-md);
}

.ai-card {
  margin-top: var(--spacing-sm);
}

.field-hint {
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
  margin-top: 4px;
}
</style>
