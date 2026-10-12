<template>
  <div class="stat-card">
    <div class="stat-header">
      <div v-if="icon" class="stat-icon" :style="{ backgroundColor: `${color}20`, color }">
        <component :is="icon" :size="22" :stroke-width="1.75" />
      </div>
      <div class="stat-info">
        <div class="stat-label">{{ label }}</div>
        <div v-if="trend" class="stat-trend" :class="{ 'is-up': trendUp }">
          {{ trendUp ? '↑' : '↓' }} {{ trend }}%
        </div>
      </div>
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="suffix" class="stat-suffix">{{ suffix }}</div>
  </div>
</template>

<script setup lang="ts">

import type { Component } from 'vue'

interface Props {
  icon?: Component
  label: string
  value: string | number
  color?: string
  suffix?: string
  trend?: number
  trendUp?: boolean
}

withDefaults(defineProps<Props>(), {
  icon: undefined,
  color: '#14b8a6',
  trendUp: true,
})
</script>

<style scoped>
.stat-card {
  padding: var(--spacing-lg);
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  transition: all var(--transition-normal);
}

.stat-card:hover {
  border-color: var(--color-primary-500);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.stat-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 24px;
  flex-shrink: 0;
}

.stat-info {
  flex: 1;
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
}

.stat-trend {
  font-size: var(--font-size-xs);
  color: var(--color-error);
}

.stat-trend.is-up {
  color: var(--color-success);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary-500);
  margin-bottom: var(--spacing-sm);
}

.stat-suffix {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
</style>
