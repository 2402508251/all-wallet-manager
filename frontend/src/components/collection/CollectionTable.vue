<template>
  <div class="card-box">
    <div class="action-bar">
      <div>
        <div class="section-title">采集记录</div>
        <div class="section-subtitle">共 {{ total }} 条，失败和待解析记录优先处理</div>
      </div>
      <div class="action-buttons">
        <el-button
          type="danger"
          size="small"
          :disabled="selectedIds.length === 0"
          @click="$emit('delete-records', selectedIds)"
        >
          删除记录 ({{ selectedIds.length }})
        </el-button>
        <el-button
          type="warning"
          size="small"
          :disabled="selectedIds.length === 0"
          @click="$emit('delete-bills', selectedIds)"
        >
          删除账单 ({{ selectedIds.length }})
        </el-button>
        <el-button type="primary" size="small" :loading="refreshing" @click="refresh">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <el-table
      v-loading="loading"
      :data="collections"
      style="width: 100%"
      size="default"
      empty-text="暂无采集记录"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="50" />
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
              <el-option label="自导出格式" value="self_export" />
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
          <template v-if="row.status === 'need_password'">
            <el-button link type="warning" size="small" @click="$emit('set-password', row)">
              输入密码
            </el-button>
          </template>
          <template v-else-if="row.status === 'pending' || row.status === 'error'">
            <el-button link type="primary" size="small" @click="$emit('parse', row)">
              解析
            </el-button>
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
import {
  channelLabel,
  channelTag,
  collectionStatusLabel,
  collectionStatusTag,
} from '@/utils/formatters'

const props = defineProps({
  collections: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

defineEmits(['parse', 'set-channel', 'set-password', 'view-result', 'delete-records', 'delete-bills'])

const collectionStore = useCollectionStore()
const refreshing = ref(false)
const selectedIds = ref([])

const currentPage = ref(1)
const currentPageSize = ref(20)

function handleSelectionChange(selection) {
  selectedIds.value = selection.map(row => row.id)
}

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

function channelTagType(channel) {
  return channelTag(channel)
}

function statusLabel(status) {
  return collectionStatusLabel(status)
}

function statusType(status) {
  return collectionStatusTag(status)
}

function isZipFile(filename) {
  return filename?.toLowerCase().endsWith('.zip')
}
</script>

<style scoped>
.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  justify-content: flex-end;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--spacing-md);
}
</style>
