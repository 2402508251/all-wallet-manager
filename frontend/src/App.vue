<template>
  <div id="app-root">
    <!-- 顶部导航栏 -->
    <el-menu
      mode="horizontal"
      :default-active="activeRoute"
      :ellipsis="false"
      class="top-nav"
      @select="handleMenuSelect"
    >
      <div class="nav-brand">统一账单</div>
      <el-menu-item index="/collection">
        <el-icon><Upload /></el-icon>
        <span>账单采集</span>
      </el-menu-item>
      <el-menu-item index="/bills">
        <el-icon><Document /></el-icon>
        <span>账单管理</span>
      </el-menu-item>
      <el-menu-item index="/accounting">
        <el-icon><Connection /></el-icon>
        <span>账务处理</span>
      </el-menu-item>
      <el-menu-item index="/reports">
        <el-icon><DataAnalysis /></el-icon>
        <span>统计报表</span>
      </el-menu-item>
      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <span>系统设置</span>
      </el-menu-item>
    </el-menu>

    <!-- 主内容区域 -->
    <div class="app-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Upload,
  Document,
  Connection,
  DataAnalysis,
  Setting,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const activeRoute = computed(() => {
  return '/' + (route.path.split('/')[1] || 'collection')
})

function handleMenuSelect(path) {
  router.push(path)
}
</script>

<style scoped>
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  height: var(--nav-height);
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-md);
}

.nav-brand {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
  margin-right: var(--spacing-xl);
  white-space: nowrap;
  user-select: none;
}
</style>
