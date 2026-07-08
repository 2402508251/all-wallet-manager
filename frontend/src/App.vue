<template>
  <div id="app-root">
    <aside class="app-sidebar">
      <div class="brand-block">
        <div class="brand-mark">账</div>
        <div>
          <div class="brand-title">统一账单</div>
          <div class="brand-subtitle">本地财务整理</div>
        </div>
      </div>

      <nav class="side-nav">
        <button
          v-for="item in navItems"
          :key="item.path"
          type="button"
          class="side-nav-item"
          :class="{ 'is-active': activeRoute === item.path }"
          @click="handleMenuSelect(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </button>
      </nav>

      <div class="privacy-note">
        <el-icon><Lock /></el-icon>
        <span>数据仅保存在本地</span>
      </div>
    </aside>

    <main class="app-main">
      <header class="app-topbar">
        <div>
          <div class="topbar-kicker">All Wallet Manager</div>
          <h1>{{ currentTitle }}</h1>
          <p>{{ currentDescription }}</p>
        </div>
      </header>

      <div class="app-content">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Odometer,
  Upload,
  Document,
  Connection,
  DataAnalysis,
  Setting,
  Lock,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/dashboard', title: '仪表盘', description: '关键财务指标与待处理事项', icon: Odometer },
  { path: '/collection', title: '账单采集', description: '上传、邮箱同步与解析入口', icon: Upload },
  { path: '/bills', title: '账单管理', description: '查询、维护、批量处理与回收站', icon: Document },
  { path: '/accounting', title: '账务处理', description: '信用、溯源与转账配对工作台', icon: Connection },
  { path: '/reports', title: '统计报表', description: '月度收支、分类分布与趋势分析', icon: DataAnalysis },
  { path: '/settings', title: '系统设置', description: '基础资料、规则和数据维护', icon: Setting },
]

const activeRoute = computed(() => {
  return '/' + (route.path.split('/')[1] || 'dashboard')
})

const currentNav = computed(() => {
  return navItems.find(item => item.path === activeRoute.value) || navItems[0]
})

const currentTitle = computed(() => route.meta?.title || currentNav.value.title)
const currentDescription = computed(() => route.meta?.description || currentNav.value.description)

function handleMenuSelect(path) {
  if (route.path !== path) router.push(path)
}
</script>

<style scoped>
#app-root {
  display: flex;
  width: 100vw;
  height: 100vh;
  min-width: var(--min-window-width);
  min-height: var(--min-window-height);
  background: var(--bg-page);
}

.app-sidebar {
  width: var(--sidebar-width);
  flex: 0 0 var(--sidebar-width);
  display: flex;
  flex-direction: column;
  padding: var(--spacing-lg) var(--spacing-md);
  color: #fff;
  background: var(--bg-shell);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0 var(--spacing-sm) var(--spacing-lg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.brand-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-lg);
  background: #fff;
  color: var(--color-primary-dark);
  font-size: var(--font-size-xl);
  font-weight: 800;
}

.brand-title {
  font-size: 18px;
  font-weight: 800;
}

.brand-subtitle,
.topbar-kicker {
  color: rgba(255, 255, 255, 0.62);
  font-size: var(--font-size-small);
}

.side-nav {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-lg) 0;
}

.side-nav-item {
  width: 100%;
  height: 42px;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  border: 0;
  border-radius: var(--radius-lg);
  padding: 0 var(--spacing-sm);
  color: rgba(255, 255, 255, 0.78);
  background: transparent;
  cursor: pointer;
  font-size: var(--font-size-base);
  font-weight: 700;
  text-align: left;
  transition: background 0.18s ease, color 0.18s ease;
}

.side-nav-item:hover,
.side-nav-item.is-active {
  color: #fff;
  background: var(--bg-shell-active);
}

.privacy-note {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: auto;
  padding: var(--spacing-sm);
  border-radius: var(--radius-lg);
  color: rgba(255, 255, 255, 0.74);
  background: rgba(255, 255, 255, 0.08);
  font-size: var(--font-size-small);
}

.app-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.app-topbar {
  height: var(--nav-height);
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-lg);
  background: rgba(255, 255, 255, 0.86);
  border-bottom: 1px solid var(--border-color-lighter);
}

.app-topbar h1 {
  color: var(--color-text-primary);
  font-size: var(--font-size-xl);
  font-weight: 800;
  line-height: 1.1;
}

.app-topbar p {
  margin-top: 3px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-small);
}

.topbar-kicker {
  color: var(--color-primary);
  font-weight: 800;
  letter-spacing: 0;
}
</style>
