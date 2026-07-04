<template>
  <div class="data-manager">
    <!-- 重新解析 -->
    <ReparsePanel @done="refreshSnapshots" />

    <!-- 数据清理 -->
    <CleanupPanel @done="refreshSnapshots" />

    <!-- 快照列表 -->
    <SnapshotList ref="snapshotRef" @restored="refreshSnapshots" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useSystemStore } from '@/stores/system'
import ReparsePanel from './ReparsePanel.vue'
import CleanupPanel from './CleanupPanel.vue'
import SnapshotList from './SnapshotList.vue'

const systemStore = useSystemStore()
const snapshotRef = ref(null)

function refreshSnapshots() {
  systemStore.loadSnapshots()
}
</script>
