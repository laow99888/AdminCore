import vue from 'eslint-plugin-vue'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'test-results/**', 'playwright-report/**'] },
  ...vue.configs['flat/essential'],
  {
    files: ['**/*.ts', '**/*.vue'],
    languageOptions: { parserOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module' } },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-debugger': 'error',
    },
  },
  { files: ['src/**/*.{ts,vue}'], rules: { '@typescript-eslint/no-explicit-any': 'error', 'no-console': ['error', { allow: ['warn', 'error'] }], 'vue/no-v-html': 'error' } },
  { files: ['**/*.ts'], languageOptions: { parser: tsParser } },
]
