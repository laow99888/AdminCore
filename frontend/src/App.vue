<template>
  <el-config-provider :locale="elementLocale">
    <div class="app-container">
      <router-view :key="locale" />
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">

import { onMounted, onBeforeUnmount, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { useThemeStore } from './stores/theme'
import { useAuthStore } from './stores/auth'
import { useModuleStore } from './stores/modules'
import { useRouter } from 'vue-router'
import { canAccessPage } from './router/access'

const themeStore = useThemeStore()
const { locale } = useI18n()
const elementLocale = computed(() => locale.value === 'en-US' ? en : zhCn)
const auth = useAuthStore()
const modules = useModuleStore()
const router = useRouter()
let refreshTimer: ReturnType<typeof setInterval> | undefined
let refreshing = false
async function refreshAccess() {
  if (refreshing || document.hidden || !localStorage.getItem('token') || !router.currentRoute.value.meta.requiresAuth) return
  refreshing = true
  try {
    await Promise.all([auth.fetchUser(true), modules.load(true)])
    window.dispatchEvent(new Event('admincore:menus-updated'))
    const path = router.currentRoute.value.path
    if (!auth.user) await router.replace(localStorage.getItem('token') ? '/unavailable' : '/login')
    else if (!modules.pathEnabled(path)) await router.replace('/')
    else if (!canAccessPage(path, auth.user)) await router.replace('/403')
  } catch { await router.replace('/unavailable') }
  finally { refreshing = false }
}

onMounted(() => {
  themeStore.initTheme()
  refreshTimer = setInterval(refreshAccess, 30000)
  window.addEventListener('focus', refreshAccess)
  document.addEventListener('visibilitychange', refreshAccess)
})
onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  window.removeEventListener('focus', refreshAccess)
  document.removeEventListener('visibilitychange', refreshAccess)
})
</script>

<style scoped>
.app-container {
  width: 100%;
  min-height: 100vh;
}
</style>
