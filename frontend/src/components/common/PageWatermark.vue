<template>
  <div v-if="visible" class="page-watermark" aria-hidden="true" data-testid="page-watermark">
    <ElWatermark :key="auth.user!.id" class="watermark-pattern" :content="content" :font="font" :gap="[70, 70]" :z-index="0" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useWatermarkStore } from '@/stores/watermark'

const auth = useAuthStore()
const theme = useThemeStore()
const watermark = useWatermarkStore()
const route = useRoute()
// 默认关闭的水印引擎仅在获准业务页实际显示时加载。
const ElWatermark = defineAsyncComponent(() => import('element-plus/es/components/watermark/index').then(module => module.ElWatermark))
const visible = computed(() => watermark.enabled && auth.isAuthenticated && !!auth.user
  && !auth.user.must_change_password && route.meta.requiresAuth === true && route.path !== '/change-password')
const content = computed(() => {
  // Canvas receives text only. Bound rendering work even for a malformed identity response.
  const value = typeof auth.user?.username === 'string' ? auth.user.username : ''
  const username = Array.from(value.replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, ''))
  return ['AdminCore', username.slice(0, 32).join('') + (username.length > 32 ? '…' : '')]
})
const font = computed(() => ({ fontSize: 14, color: theme.isDark ? 'rgba(255,255,255,0.13)' : 'rgba(0,0,0,0.10)' }))
</script>

<style scoped>
.page-watermark {
  position: fixed;
  inset: 0;
  z-index: 1000;
  pointer-events: none;
  overflow: hidden;
}
.watermark-pattern { width: 100%; height: 100%; pointer-events: none; }
</style>
