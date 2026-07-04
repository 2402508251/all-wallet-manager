// router/index.js — Hash 模式路由配置

import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/collection' },
  {
    path: '/collection',
    component: () => import('@/views/CollectionView.vue'),
    meta: { title: '账单采集', icon: 'Upload' },
  },
  {
    path: '/bills',
    component: () => import('@/views/BillListView.vue'),
    meta: { title: '账单管理', icon: 'Document' },
  },
  {
    path: '/accounting',
    component: () => import('@/views/AccountingView.vue'),
    meta: { title: '账务处理', icon: 'Connection' },
  },
  {
    path: '/reports',
    component: () => import('@/views/ReportView.vue'),
    meta: { title: '统计报表', icon: 'DataAnalysis' },
  },
  {
    path: '/settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '系统设置', icon: 'Setting' },
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
