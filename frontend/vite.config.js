import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    open: true,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    chunkSizeWarningLimit: 950,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('zrender')) {
            return 'vendor-zrender'
          }

          if (id.includes('echarts')) {
            return 'vendor-echarts'
          }

          if (id.includes('element-plus')) {
            return 'vendor-element-plus'
          }

          if (id.includes('@element-plus/icons-vue')) {
            return 'vendor-element-icons'
          }

          if (
            id.includes('/vue/') ||
            id.includes('\\vue\\') ||
            id.includes('vue-router') ||
            id.includes('pinia')
          ) {
            return 'vendor-vue'
          }
        },
      },
    },
  },
})
