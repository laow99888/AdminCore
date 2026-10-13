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
      include: ['src/components/common/Base{Form,Table,Dialog}.vue'],
      reporter: ['text', 'html', 'json-summary'],
      thresholds: { statements: 80, branches: 70, functions: 80, lines: 80 },
    },
  },
})
