<template>
  <main class="service-error">
    <div>
      <h1>{{ forbidden ? '403' : '500' }}</h1>
      <h2>{{ uiText(forbidden ? '没有访问此页面的权限' : '服务暂时不可用') }}</h2>
      <p>{{ uiText(forbidden ? '请联系管理员确认权限' : '请稍后重试') }}</p>
      <el-button type="primary" @click="retry">{{ uiText(forbidden ? '返回首页' : '重试') }}</el-button>
      <el-button @click="router.push('/login')">{{ uiText('登录') }}</el-button>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { uiText } from '@/i18n/uiText'

const router = useRouter()
const route = useRoute()
const forbidden = computed(() => route.path === '/403')
const retry = () => router.push('/')
</script>

<style scoped>
.service-error { display: grid; place-items: center; min-height: 100dvh; padding: var(--spacing-lg); text-align: center; background: var(--color-bg-page); color: var(--color-text-primary); }
h1 { font-size: clamp(64px, 15vw, 120px); color: var(--color-primary-500); margin: 0; }
p { color: var(--color-text-secondary); }
</style>
