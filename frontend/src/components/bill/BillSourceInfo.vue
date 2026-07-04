<template>
  <div v-if="sourceBill" class="source-info">
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="源渠道">
        <el-tag size="small">{{ channelLabel(sourceBill.channel) }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <h4 class="section-title">原始记录 (JSON)</h4>
    <div class="json-viewer">
      <pre>{{ formattedJson }}</pre>
    </div>
  </div>
  <el-empty v-else description="无源账单数据" :image-size="80" />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sourceBill: { type: Object, default: null },
})

const formattedJson = computed(() => {
  if (!props.sourceBill?.raw_json) return ''
  try {
    const obj = typeof props.sourceBill.raw_json === 'string'
      ? JSON.parse(props.sourceBill.raw_json)
      : props.sourceBill.raw_json
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(props.sourceBill.raw_json)
  }
})

function channelLabel(ch) {
  const map = { wechat: '微信', alipay: '支付宝', ccb: '建行' }
  return map[ch] || ch
}
</script>

<style scoped>
.source-info {
  padding: var(--spacing-sm);
}

.section-title {
  margin: var(--spacing-md) 0 var(--spacing-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
}

.json-viewer {
  background: #f5f7fa;
  border-radius: var(--radius-base);
  padding: var(--spacing-md);
  max-height: 300px;
  overflow: auto;
}

.json-viewer pre {
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
