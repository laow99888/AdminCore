<template>
  <fieldset class="table-density-settings">
    <legend>{{ uiText('表格密度') }}</legend>
    <p class="density-description">{{ uiText('应用于通用表格，仅保存在当前浏览器。') }}</p>
    <div class="density-options">
      <label v-for="option in options" :key="option.value" :class="{ selected: preferences.density === option.value }">
        <input type="radio" name="table-density" :value="option.value" :checked="preferences.density === option.value" @change="preferences.setDensity(option.value)" />
        <span>{{ uiText(option.label) }}</span>
      </label>
    </div>
    <p v-if="preferences.persistenceUnavailable" role="status" class="density-description">
      {{ uiText('浏览器未允许保存偏好，本次页面内仍可使用。') }}
    </p>
  </fieldset>
</template>

<script setup lang="ts">
import { uiText } from '@/i18n/uiText'
import { useTablePreferencesStore } from '@/stores/tablePreferences'

const preferences = useTablePreferencesStore()
const options = [
  { value: 'comfortable', label: '舒适' },
  { value: 'compact', label: '紧凑' },
] as const
</script>

<style scoped>
.table-density-settings { min-width: 0; margin: 0; padding: 0; border: 0; }
legend { font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
.density-description { margin: var(--spacing-xs) 0 var(--spacing-md); color: var(--color-text-secondary); font-size: var(--font-size-sm); overflow-wrap: anywhere; }
.density-options { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); }
.density-options label { display: flex; align-items: center; justify-content: center; gap: var(--spacing-sm); box-sizing: border-box; min-height: 44px; min-width: 88px; padding: var(--spacing-sm) var(--spacing-lg); border: 1px solid var(--color-border-dark); border-radius: var(--radius-md); background: var(--color-bg-card); color: var(--color-text-primary); cursor: pointer; }
.density-options label.selected { border-color: var(--color-primary-600); background: var(--color-bg-elevated); }
.density-options label:focus-within { outline: 2px solid var(--color-primary-600); outline-offset: 2px; }
.density-options input { margin: 0; accent-color: var(--color-primary-600); }
</style>
