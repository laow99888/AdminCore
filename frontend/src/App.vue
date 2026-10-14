<template>
  <el-config-provider :locale="elementLocale">
    <div class="app-container">
      <AppErrorBoundary ref="errorBoundary" :reset-key="router.currentRoute.value.path + ':' + navigation.epoch" :route-path="router.currentRoute.value.path" @home="returnHome">
        <router-view v-slot="{ Component, route: viewRoute }">
          <KeepAlive :key="navigation.epoch" :include="cacheIncludes" :max="1">
            <component :is="Component" :key="viewRoute.path + ':' + (viewRoute.meta.preserveOnLocaleChange ? '' : locale)" />
          </KeepAlive>
        </router-view>
      </AppErrorBoundary>
      <PageWatermark />
      <KeyboardShortcuts />
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">

import { onMounted, onBeforeUnmount, computed, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { useAuthStore } from './stores/auth'
import { useModuleStore } from './stores/modules'
import { useRouter } from 'vue-router'
import { canAccessPage } from './router/access'
import { useNavigationStore } from './stores/navigation'
import AppErrorBoundary from './components/common/AppErrorBoundary.vue'
import PageWatermark from './components/common/PageWatermark.vue'
import KeyboardShortcuts from './components/common/KeyboardShortcuts.vue'

const { locale } = useI18n()
const elementLocale = computed(() => locale.value === 'en-US' ? en : zhCn)
const auth = useAuthStore()
const modules = useModuleStore()
const router = useRouter()
const navigation = useNavigationStore()
const errorBoundary = ref<InstanceType<typeof AppErrorBoundary>>()
function showRootError() { errorBoundary.value?.captureError() }
function returnHome() { void router.push('/').catch(() => {}) }
const cacheIncludes = computed(() => navigation.tabs.some(tab => tab.path === '/logs') ? ['OperationLogView'] : [])
watch(() => JSON.stringify([auth.token, auth.user?.id, auth.user?.must_change_password,
  auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, modules.config]), () => {
  if (auth.preservingSecuritySession && ['/settings/two-factor', '/login'].includes(router.currentRoute.value.path)) return
  navigation.clear()
}, { flush: 'sync' })
let refreshTimer: ReturnType<typeof setInterval> | undefined
let refreshing = false
async function refreshAccess() {
  if (refreshing || document.hidden || !localStorage.getItem('token') || !router.currentRoute.value.meta.requiresAuth) return
  refreshing = true
  try {
    await auth.fetchUser(true)
    if (!auth.user) {
      await router.replace(localStorage.getItem('token') ? '/unavailable' : '/login')
      return
    }
    if (auth.user.must_change_password) {
      if (router.currentRoute.value.path !== '/change-password') await router.replace('/change-password')
      return
    }
    await modules.load(true)
    window.dispatchEvent(new Event('admincore:menus-updated'))
    navigation.prune(path => modules.pathEnabled(path) && canAccessPage(path, auth.user))
    const path = router.currentRoute.value.path
    if (!auth.user) await router.replace(localStorage.getItem('token') ? '/unavailable' : '/login')
    else if (!modules.pathEnabled(path)) await router.replace('/')
    else if (!canAccessPage(path, auth.user)) await router.replace('/403')
  } catch { await router.replace('/unavailable') }
  finally { refreshing = false }
}

onMounted(() => {
  refreshTimer = setInterval(refreshAccess, 30000)
  window.addEventListener('focus', refreshAccess)
  document.addEventListener('visibilitychange', refreshAccess)
})
window.addEventListener('admincore:session-cleared', navigation.clear)
window.addEventListener('admincore:vue-error', showRootError)
onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  window.removeEventListener('focus', refreshAccess)
  document.removeEventListener('visibilitychange', refreshAccess)
  window.removeEventListener('admincore:session-cleared', navigation.clear)
  window.removeEventListener('admincore:vue-error', showRootError)
})
</script>

<style scoped>
.app-container {
  width: 100%;
  min-height: 100vh;
}
</style>
