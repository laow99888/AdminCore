<template>
  <div class="not-found-container flex-center">
    <div class="error-content text-center">
      <div class="error-code">404</div>
      <h1 class="error-title">{{ uiText("页面不存在") }}</h1>
      <p class="error-message">{{ uiText("抱歉，您访问的页面不存在或已被删除") }}</p>
      <el-button type="primary" @click="goHome">{{ uiText("返回首页") }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { useRouter } from 'vue-router'

const router = useRouter()

const goHome = () => {
  router.push('/')
}
</script>

<style scoped>
.not-found-container {
  width: 100%;
  height: 100vh;
  background: var(--color-bg-page);
}

.error-content {
  text-align: center;
}

.error-code {
  font-size: 120px;
  font-weight: var(--font-weight-bold);
  color: var(--color-primary-500);
  opacity: 0.1;
  line-height: 1;
}

.error-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-md);
}

.error-message {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-xl);
}
</style>
