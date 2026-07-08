// router/index.js — Hash 模式路由配置

import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '仪表盘', description: '关键财务指标、近期交易和待处理事项' },
  },
  {
    path: '/collection',
    component: () => import('@/views/CollectionView.vue'),
    meta: { title: '账单采集', description: '上传、邮箱同步与解析入口' },
  },
  {
    path: '/bills',
    component: () => import('@/views/BillListView.vue'),
    meta: { title: '账单管理', description: '查询、维护、批量处理与回收站' },
  },
  {
    path: '/accounting',
    component: () => import('@/views/AccountingView.vue'),
    meta: { title: '账务处理', description: '信用、溯源与转账配对工作台' },
  },
  {
    path: '/reports',
    component: () => import('@/views/ReportView.vue'),
    meta: { title: '统计报表', description: '月度收支、分类分布与趋势分析' },
  },
  {
    path: '/settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '系统设置', description: '基础资料、规则和数据维护' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 导航守卫：更新页面标题
router.beforeEach((to, from, next) => {
  if (to.meta?.title) {
    document.title = `${to.meta.title} - 统一账单`
  }
  next()
})

export default router
