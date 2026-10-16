import { defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default defineConfig({
  ...viteConfig,
  test: {
    environment: 'jsdom',
    server: { deps: { inline: [/element-plus/] } },
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      // R1：覆盖率统计纳入所有产品源码，避免基础组件门槛被误读为全前端覆盖率。
      include: ['src/**/*.{ts,vue}'],
      reporter: ['text', 'html', 'json-summary'],
      // 门禁略低于 2026-10-17 实测基线，防止后续改动回退覆盖率，同时给测试运行环境保留小幅波动空间。
      thresholds: { statements: 36, branches: 33, functions: 30, lines: 39 },
    },
  },
})
