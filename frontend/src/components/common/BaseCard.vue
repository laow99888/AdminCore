<template>
  <div class="base-card" :class="{ 'is-hoverable': hoverable }">
    <!-- 卡片头部 -->
    <div v-if="title || $slots.header" class="card-header">
      <slot name="header">
        <div class="card-title">{{ title }}</div>
        <div v-if="$slots.extra" class="card-extra">
          <slot name="extra"></slot>
        </div>
      </slot>
    </div>

    <!-- 卡片内容 -->
    <div class="card-body">
      <slot></slot>
    </div>

    <!-- 卡片底部 -->
    <div v-if="$slots.footer" class="card-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">

interface Props {
  title?: string
  hoverable?: boolean
}

withDefaults(defineProps<Props>(), {
  hoverable: false,
})
</script>

<style scoped>
.base-card {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  overflow: hidden;
  transition: all var(--transition-normal);
}

.base-card.is-hoverable:hover {
  border-color: var(--color-primary-500);
  box-shadow: var(--shadow-lg);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  gap: var(--spacing-md);
}

.card-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.card-extra {
  margin-left: auto;
}

.card-body {
  padding: var(--spacing-lg);
}

.card-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
  background-color: var(--color-bg-elevated);
}
</style>
