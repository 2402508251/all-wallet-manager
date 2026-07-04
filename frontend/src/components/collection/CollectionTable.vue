<template>
  <div class="card-box">
    <div class="action-bar">
      <h3>采集结果列表 (共 {{ total }} 条)</h3>
      <el-button type="primary" size="small" :loading="refreshing" @click="refresh">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="collections"
      style="width: 100%"
      size="default"
      empty-text="暂无采集记录"
    >
      <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
      <el-table-column label="渠道" width="120">
        <template #default="{ row }">
          <template v-if="row.channel === 'unknown'">
            <el-select
              size="small"
              placeholder="选择渠道"
              style="width: 100px"
              @change="(val) => handleSetChannel(row, val)"
            >
              <el-option label="微信" value="wechat" />
              <el-option label="支付宝" value="alipay" />
              <el-option label="建行" value="ccb" />
            </el-select>
          </template>
          <el-tag v-else size="small" :type="channelTagType(row.channel)">
            {{ channelLabel(row.channel) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending' || row.status === 'error'">
            <template v-if="isZipFile(row.file_name) && !row.is_extracted">
              <el-button link type="warning" size="small" @click="$emit('set-password', row)">
                输入密码
              </el-button>
            </template>
            <template v-else>
              <el-button link type="primary" size="small" @click="$emit('parse', row)">
                解析
              </el-button>
            </template>
          </template>
          <!-- 已解析的可以查看 -->
          <el-button
            v-if="row.status === 'parsed'"
            link
            type="success"
            size="small"
            @click="$emit('view-result', row)"
          >
            查看结果
          </el-button>
          <!-- 错误显示错误信息 -->
          <el-tooltip
            v-if="row.status === 'error' && row.error_msg"
            :content="row.error_msg"
          >
            <el-button link type="danger" size="small">错误详情</el-button>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="80">
        <template #default="{ row }">
          {{ row.source_type === 'email' ? '邮箱' : '上传' }}
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">
          {{ row.created_at ? row.created_at.slice(0, 16).replace('T', ' ') : '' }}
        </template>
      </el-table-column>
    </el-table>

    <div class="table-footer">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="currentPageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        small
        @size-change="handlePageSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useCollectionStore } from '@/stores/collection'

const props = defineProps({
  collections: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

defineEmits(['parse', 'set-channel', 'set-password', 'view-result'])

const collectionStore = useCollectionStore()
const refreshing = ref(false)

const currentPage = ref(1)
const currentPageSize = ref(20)

function refresh() {
  refreshing.value = true
  collectionStore.loadCollections().finally(() => {
    refreshing.value = false
  })
}

function handlePageChange(page) {
  currentPage.value = page
  collectionStore.loadCollections(page, currentPageSize.value)
}

function handlePageSizeChange(size) {
  currentPageSize.value = size
  collectionStore.loadCollections(1, size)
}

async function handleSetChannel(row, channel) {
  await collectionStore.setChannelManual(row.id, channel)
  row.channel = channel
}

function channelLabel(channel) {
  const map = { wechat: '微信', alipay: '支付宝', ccb: '建行', unknown: '未知' }
  return map[channel] || channel
}

function channelTagType(channel) {
  const map = { wechat: 'success', alipay: 'primary', ccb: 'warning' }
  return map[channel] || 'info'
}

function statusLabel(status) {
  const map = { pending: '待解析', parsing: '解析中', parsed: '已解析', error: '失败' }
  return map[status] || status
}

function statusType(status) {
  const map = { pending: 'info', parsing: 'warning', parsed: 'success', error: 'danger' }
  return map[status] || 'info'
}

function isZipFile(filename) {
  return filename?.toLowerCase().endsWith('.zip')
}

function isPdfFile(filename) {
  return filename?.toLowerCase().endsWith('.pdf')
}
</script>

<style scoped>
.table-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--spacing-md);
}
</style>