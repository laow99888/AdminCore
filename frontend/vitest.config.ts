import { defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default defineConfig({
  ...viteConfig,
  test: {
    environment: 'jsdom',
    maxWorkers: 4,
    server: { deps: { inline: [/element-plus/] } },
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      // R1：覆盖率统计纳入所有产品源码，避免基础组件门槛被误读为全前端覆盖率。
      include: ['src/**/*.{ts,vue}'],
      reporter: ['text', 'html', 'json-summary'],
      // 门禁略低于 2026-10-17 实测基线，防止后续改动回退覆盖率，同时给测试运行环境保留小幅波动空间。
      thresholds: {
        statements: 54, branches: 50, functions: 47, lines: 56,
        // 关键链路独立守住已测基线，避免全局平均值掩盖认证或基础组件回退。
        'src/auth/**/*.ts': { statements: 89, branches: 86, functions: 94, lines: 96 },
        'src/stores/auth.ts': { statements: 85, branches: 75, functions: 88, lines: 93 },
        'src/api/request.ts': { statements: 73, branches: 58, functions: 96, lines: 79 },
        'src/utils/realtime.ts': { statements: 84, branches: 77, functions: 80, lines: 92 },
        'src/components/common/Base{Form,Table}.vue': {
          perFile: true, statements: 95, branches: 92, functions: 98, lines: 98,
        },
      },
    },
  },
})
