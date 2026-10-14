<template>
  <section class="theme-color-settings" aria-labelledby="theme-color-label">
    <h3 id="theme-color-label">{{ uiText('主题主色') }}</h3>
    <p id="theme-color-description">{{ uiText('仅保存在本浏览器。应用时会按明暗模式调整色阶，保证自定义主色按钮和重要文字的可读性。') }}</p>
    <div class="theme-color-controls">
      <input v-model="draft" type="color" :aria-label="uiText('选择主题颜色')" />
      <el-input v-model="draft" maxlength="7" :aria-label="uiText('主题颜色十六进制值')" aria-describedby="theme-color-description" :aria-invalid="!!error" @keyup.enter="apply" />
      <el-button type="primary" @click="apply">{{ uiText('应用主题颜色') }}</el-button>
      <el-button :disabled="!theme.primaryColor" @click="reset">{{ uiText('恢复默认主色') }}</el-button>
    </div>
    <p v-if="error" role="alert">{{ uiText('请输入完整的 #RRGGBB 颜色值，例如 #2563EB。') }}</p>
    <p v-if="theme.primaryColor" class="theme-color-applied" role="status">{{ uiText('当前模式实际主色：{p0}', { p0: appliedColor }) }}</p>
    <p v-if="!theme.persistenceAvailable" role="status">{{ uiText('浏览器无法保存主题偏好，当前选择仅在本次页面会话内生效。') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { uiText } from '@/i18n/uiText'
import { useThemeStore } from '@/stores/theme'
import { createThemePalette, DEFAULT_PRIMARY_COLOR } from '@/utils/themeColors'

const theme = useThemeStore()
const draft = ref(theme.primaryColor || DEFAULT_PRIMARY_COLOR)
const error = ref(false)
const appliedColor = computed(() => theme.primaryColor ? createThemePalette(theme.primaryColor, theme.isDark).primary : DEFAULT_PRIMARY_COLOR)
watch(() => theme.primaryColor, value => { draft.value = value || DEFAULT_PRIMARY_COLOR })
watch(draft, () => { error.value = false })
function apply() { error.value = !theme.setPrimaryColor(draft.value) }
function reset() { theme.resetPrimaryColor(); draft.value = DEFAULT_PRIMARY_COLOR; error.value = false }
</script>

<style scoped>
.theme-color-settings { padding: var(--spacing-md) 0; }
h3 { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); }
p { margin: var(--spacing-xs) 0; font-size: var(--font-size-sm); color: var(--color-text-secondary); overflow-wrap: anywhere; }
.theme-color-controls { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); margin-top: var(--spacing-md); align-items: center; }
input[type='color'] { width: 44px; height: 44px; padding: var(--spacing-xs); background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); cursor: pointer; }
input[type='color']:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.theme-color-controls :deep(.el-input) { width: 148px; min-width: 0; }
.theme-color-controls :deep(.el-input__wrapper), .theme-color-controls :deep(.el-button) { min-height: 44px; }
.theme-color-controls :deep(.el-button + .el-button) { margin-left: 0; }
[role='alert'] { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
@media (max-width: 480px) { .theme-color-controls :deep(.el-button) { white-space: normal; height: auto; max-width: 100%; padding: var(--spacing-sm) var(--spacing-md); } }
</style>
