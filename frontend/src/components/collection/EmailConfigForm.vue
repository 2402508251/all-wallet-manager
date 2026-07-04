<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="100px"
    size="default"
  >
    <el-form-item label="邮箱类型">
      <el-select
        v-model="selectedTemplate"
        placeholder="选择邮箱类型自动填充"
        clearable
        style="width: 100%"
        @change="handleTemplateChange"
      >
        <el-option
          v-for="t in templates"
          :key="t.key"
          :label="t.label"
          :value="t.key"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="邮箱地址" prop="email_addr">
      <el-input v-model="form.email_addr" placeholder="请输入邮箱地址" @blur="autoDetectTemplate" />
    </el-form-item>
    <el-form-item label="IMAP服务器" prop="imap_server">
      <el-input v-model="form.imap_server" placeholder="如 imap.qq.com" />
    </el-form-item>
    <el-form-item label="IMAP端口" prop="imap_port">
      <el-input-number
        v-model="form.imap_port"
        :min="1"
        :max="65535"
        placeholder="993"
      />
    </el-form-item>
    <el-form-item label="授权码" prop="auth_code">
      <el-input
        v-model="form.auth_code"
        type="password"
        show-password
        placeholder="请输入邮箱授权码"
      />
      <div class="auth-code-hint" v-if="selectedTemplate">
        {{ currentTemplateHint }}
      </div>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'

const props = defineProps({
  initialData: {
    type: Object,
    default: () => ({}),
  },
})

const formRef = ref(null)

const templates = [
  {
    key: 'qq',
    label: 'QQ邮箱',
    domain: 'qq.com',
    imap_server: 'imap.qq.com',
    imap_port: 993,
    hint: '在 QQ邮箱 → 设置 → 账户 → POP3/IMAP/SMTP 中开启服务并获取授权码',
  },
  {
    key: '163',
    label: '163邮箱',
    domain: '163.com',
    imap_server: 'imap.163.com',
    imap_port: 993,
    hint: '在 163邮箱 → 设置 → POP3/IMAP/SMTP 中开启 IMAP 服务并获取授权码',
  },
  {
    key: '126',
    label: '126邮箱',
    domain: '126.com',
    imap_server: 'imap.126.com',
    imap_port: 993,
    hint: '在 126邮箱 → 设置 → POP3/IMAP/SMTP 中开启 IMAP 服务并获取授权码',
  },
  {
    key: 'yeah',
    label: 'Yeah邮箱',
    domain: 'yeah.net',
    imap_server: 'imap.yeah.net',
    imap_port: 993,
    hint: '在 Yeah邮箱 → 设置 → POP3/IMAP/SMTP 中开启 IMAP 服务并获取授权码',
  },
  {
    key: 'sina',
    label: '新浪邮箱',
    domain: 'sina.com',
    imap_server: 'imap.sina.com',
    imap_port: 993,
    hint: '在 新浪邮箱 → 设置 → 账户 → IMAP/SMTP 中开启服务并获取授权码',
  },
  {
    key: 'outlook',
    label: 'Outlook / Hotmail',
    domain: 'outlook.com',
    imap_server: 'outlook.office365.com',
    imap_port: 993,
    hint: 'Outlook/Hotmail 默认已开启 IMAP，使用应用密码登录',
  },
  {
    key: 'gmail',
    label: 'Gmail',
    domain: 'gmail.com',
    imap_server: 'imap.gmail.com',
    imap_port: 993,
    hint: '在 Google 账户 → 安全 → 应用密码 中生成应用专用密码',
  },
]

const selectedTemplate = ref('')

const form = reactive({
  email_addr: props.initialData.email_addr || '',
  imap_server: props.initialData.imap_server || '',
  imap_port: props.initialData.imap_port || 993,
  auth_code: '',
})

const currentTemplateHint = computed(() => {
  const t = templates.find(t => t.key === selectedTemplate.value)
  return t ? t.hint : ''
})

const rules = {
  email_addr: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  imap_server: [
    { required: true, message: '请输入IMAP服务器地址', trigger: 'blur' },
  ],
  imap_port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
  ],
  auth_code: [
    { required: true, message: '请输入授权码', trigger: 'blur' },
    { min: 6, message: '授权码至少6位', trigger: 'blur' },
  ],
}

function handleTemplateChange(key) {
  if (!key) return
  const t = templates.find(t => t.key === key)
  if (!t) return
  form.imap_server = t.imap_server
  form.imap_port = t.imap_port
  if (!form.email_addr && t.domain) {
    form.email_addr = `@${t.domain}`
  }
}

function autoDetectTemplate() {
  const email = form.email_addr.trim()
  if (!email) return
  const domain = email.split('@')[1]
  if (!domain) return
  const matched = templates.find(t => t.domain === domain)
  if (matched) {
    selectedTemplate.value = matched.key
    form.imap_server = matched.imap_server
    form.imap_port = matched.imap_port
  }
}

function validate() {
  return formRef.value?.validate()
}

function resetFields() {
  formRef.value?.resetFields()
  selectedTemplate.value = ''
}

function getFormData() {
  return {
    email: form.email_addr,
    imap_server: form.imap_server,
    imap_port: form.imap_port,
    auth_code: form.auth_code,
  }
}

defineExpose({ validate, resetFields, getFormData })
</script>

<style scoped>
.auth-code-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  margin-top: 4px;
}
</style>