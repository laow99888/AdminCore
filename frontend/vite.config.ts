import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { cpSync, mkdirSync } from 'node:fs'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [vue(), Components({ dts: false, resolvers: [ElementPlusResolver()] }), {
    name: 'pdf-preview-assets',
    closeBundle() {
      // 与锁定的 PDF.js 版本一起发布 CMap/字体/解码器及许可证，不使用第三方 CDN。
      const source = path.resolve(import.meta.dirname, 'node_modules/pdfjs-dist')
      const target = path.resolve(import.meta.dirname, 'dist/pdf-assets')
      mkdirSync(target, { recursive: true })
      for (const directory of ['cmaps', 'standard_fonts', 'wasm']) cpSync(path.join(source, directory), path.join(target, directory), { recursive: true })
      cpSync(path.join(source, 'LICENSE'), path.join(target, 'LICENSE'))
      cpSync(path.resolve(import.meta.dirname, 'third-party/richtext'), path.resolve(import.meta.dirname, 'dist/third-party/richtext'), { recursive: true })
      cpSync(path.resolve(import.meta.dirname, 'third-party/sheetjs'), path.resolve(import.meta.dirname, 'dist/third-party/sheetjs'), { recursive: true })
    },
  }],
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
            { name: 'pdf-preview', test: /node_modules[\\/]pdfjs-dist[\\/]/, priority: 30, entriesAware: true },
            { name: 'element', test: /node_modules[\\/](@element-plus|element-plus)[\\/]/, priority: 20, entriesAware: true, maxSize: 1000000 },
            { name: 'vendor', test: /node_modules/, priority: 10, entriesAware: true, maxSize: 800000 },
          ],
        },
      },
    },
  },
})
