import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { cpSync, mkdirSync, writeFileSync } from 'node:fs'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const profile = process.env.ADMINCORE_BUILD_PROFILE ?? 'full'
if (!['full', 'minimal'].includes(profile)) throw new Error('ADMINCORE_BUILD_PROFILE must be full or minimal')
const minimal = profile === 'minimal'
const microFrontendsEnabled = process.env.ADMINCORE_MICRO_FRONTENDS_ENABLED === 'true'
let buildOutput = path.resolve(import.meta.dirname, 'dist')

export default defineConfig({
  define: {
    __ADMINCORE_MINIMAL_BUILD__: JSON.stringify(minimal),
    __ADMINCORE_MICRO_FRONTENDS_ENABLED__: JSON.stringify(microFrontendsEnabled),
  },
  plugins: [vue(), Components({ dts: false, resolvers: [ElementPlusResolver()] }), {
    name: 'pdf-preview-assets',
    apply: 'build',
    configResolved(config) { buildOutput = path.resolve(config.root, config.build.outDir) },
    closeBundle() {
      const output = buildOutput
      mkdirSync(output, { recursive: true })
      writeFileSync(path.join(output, 'build-profile.json'), JSON.stringify({ profile }))
      if (minimal) return
      // 与锁定的 PDF.js 版本一起发布 CMap/字体/解码器及许可证，不使用第三方 CDN。
      const source = path.resolve(import.meta.dirname, 'node_modules/pdfjs-dist')
      const target = path.join(output, 'pdf-assets')
      mkdirSync(target, { recursive: true })
      for (const directory of ['cmaps', 'standard_fonts', 'wasm']) cpSync(path.join(source, directory), path.join(target, directory), { recursive: true })
      cpSync(path.join(source, 'LICENSE'), path.join(target, 'LICENSE'))
      cpSync(path.resolve(import.meta.dirname, 'third-party/richtext'), path.join(output, 'third-party/richtext'), { recursive: true })
      cpSync(path.resolve(import.meta.dirname, 'third-party/sheetjs'), path.join(output, 'third-party/sheetjs'), { recursive: true })
    },
  }],
  resolve: {
    alias: [
      ...(minimal ? ['@/router/moduleRoutes', '@/modules/registry'].map(find => ({ find, replacement: path.resolve(import.meta.dirname, './src/modules/minimal.ts') })) : []),
      ...(minimal ? [{ find: '@/components/common/LocalExportButton.vue', replacement: path.resolve(import.meta.dirname, './src/components/common/OmittedLocalExport.ts') }] : []),
      { find: '@', replacement: path.resolve(import.meta.dirname, './src') },
    ],
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
    terserOptions: { compress: { passes: 3 } },
    manifest: true,
    rolldownOptions: {
      output: {
          // 共享块的自动名称会拼接多页名称；截短前缀，保留内容哈希，减少首屏预加载路径体积。
          chunkFileNames: chunk => `assets/${chunk.name.slice(0, 64)}-[hash].js`,
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
