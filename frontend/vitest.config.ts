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
      // 当前基线是全量统计的下限，随关键业务回归增加逐步提升，不以测试数量代替风险覆盖。
      thresholds: { statements: 25, branches: 15, functions: 25, lines: 25 },
    },
  },
})
