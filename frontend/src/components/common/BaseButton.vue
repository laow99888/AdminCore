<template>
  <el-button
    class="base-button"
    :class="[`variant-${variant}`, `size-${size}`]"
    :type="buttonType"
    :loading="loading"
    :disabled="disabled"
    :icon="icon"
    v-bind="$attrs"
  >
    <slot></slot>
  </el-button>
</template>

<script setup lang="ts">

import { computed, type Component } from 'vue'

type ButtonType = 'default' | 'primary' | 'success' | 'warning' | 'danger'

interface Props {
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
  size?: 'small' | 'default' | 'large'
  loading?: boolean
  disabled?: boolean
  icon?: string | Component
  type?: ButtonType
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'default',
  loading: false,
  disabled: false,
  type: 'default',
})

const buttonType = computed(() => {
  if (props.type === 'default') return 'default'
  return props.type
})
</script>

<style scoped>
.base-button {
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-semibold);
  transition: all var(--transition-fast);
}

/* 按钮大小 */
.size-small {
  --el-button-size: 28px;
  font-size: var(--font-size-xs);
}

.size-default {
  --el-button-size: 36px;
  font-size: var(--font-size-sm);
}

.size-large {
  --el-button-size: 44px;
  font-size: var(--font-size-base);
}

/* 按钮风格 */
.variant-primary {
  --el-button-text-color: var(--admincore-primary-on-color, var(--color-dark-950));
  --el-button-hover-text-color: var(--admincore-primary-on-color, var(--color-dark-950));
  --el-button-active-text-color: var(--admincore-primary-on-color, var(--color-dark-950));
  --el-button-disabled-text-color: var(--admincore-primary-on-color, var(--color-dark-950));
  background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
  border: none;
}

.variant-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px color-mix(in srgb, var(--color-primary-500) 30%, transparent);
}

.variant-primary:active:not(:disabled) {
  transform: scale(0.98);
}

.variant-ghost {
  background-color: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-primary);
}

.variant-ghost:hover:not(:disabled) {
  background-color: var(--color-bg-elevated);
  border-color: var(--color-primary-500);
  color: var(--color-primary-500);
}

.variant-danger {
  background-color: #ef4444;
  border-color: #ef4444;
}

.variant-danger:hover:not(:disabled) {
  background-color: #dc2626;
  border-color: #dc2626;
}
</style>
