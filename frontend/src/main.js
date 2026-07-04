// main.js — Vue 应用入口（等待 Bridge 就绪后挂载）

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import '@/styles/variables.css'
import '@/styles/reset.css'
import '@/styles/global.css'
import '@/styles/element-overrides.css'
import App from './App.vue'
import router from './router'
import { ready } from '@/utils/bridge'

async function bootstrap() {
  // 等待 PyWebView Bridge 就绪（非 PyWebView 环境直接通过）
  if (window.pywebview !== undefined) {
    await ready()
  }

  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  app.use(router)
  app.use(ElementPlus, { locale: zhCn })
  app.mount('#app')
}

bootstrap()
