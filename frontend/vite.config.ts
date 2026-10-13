import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [vue(), Components({ dts: false, resolvers: [ElementPlusResolver()] })],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'terser',
    manifest: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            // 图表内部模块存在初始化依赖，保持同一懒加载块，避免按大小拆分导致执行顺序错误。
            { name: 'charts', test: /node_modules[\\/](echarts|zrender)[\\/]/, priority: 30 },
            { name: 'element', test: /node_modules[\\/](@element-plus|element-plus)[\\/]/, priority: 20, entriesAware: true, maxSize: 1000000 },
            { name: 'vendor', test: /node_modules/, priority: 10, entriesAware: true, maxSize: 800000 },
          ],
        },
      },
    },
  },
})
