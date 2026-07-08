<template>
  <div class="data-manager">
    <!-- 重新解析 -->
    <ReparsePanel @done="refreshSnapshots" />

    <!-- 重新分类 -->
    <RecategorizePanel @done="refreshSnapshots" />

    <!-- 数据清理 -->
    <CleanupPanel @done="refreshSnapshots" />

    <!-- 重置应用 -->
    <ResetApplicationPanel @done="refreshSnapshots" />

    <!-- 快照列表 -->
    <SnapshotList ref="snapshotRef" @restored="refreshSnapshots" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useSystemStore } from '@/stores/system'
import ReparsePanel from './ReparsePanel.vue'
import RecategorizePanel from './RecategorizePanel.vue'
import CleanupPanel from './CleanupPanel.vue'
import ResetApplicationPanel from './ResetApplicationPanel.vue'
import SnapshotList from './SnapshotList.vue'

const systemStore = useSystemStore()
const snapshotRef = ref(null)

function refreshSnapshots() {
  systemStore.loadSnapshots()
}
</script>
