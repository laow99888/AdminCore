<template>
  <div class="app-layout">
    <AppSidebar />
    <div class="layout-main">
      <AppHeader />
      <NavigationTabs />
      <main class="layout-content">
        <slot></slot>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">

import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
import NavigationTabs from './NavigationTabs.vue'
</script>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  background-color: var(--color-bg-page);
  transition: background-color var(--transition-normal);
}

.layout-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  width: 0; /* 关键：解决 flex 布局溢出问题 */
}

.layout-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xl);
  background: linear-gradient(135deg, var(--color-bg-page) 0%, var(--color-bg-elevated) 100%);
}

/* 响应式：移动设备 */
@media (max-width: 768px) {
  .layout-content {
    padding: var(--spacing-lg);
  }
}
</style>
