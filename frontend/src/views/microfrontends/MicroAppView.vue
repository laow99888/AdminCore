<template>
  <section class="micro-app-shell" :aria-label="app?.name || '微前端应用'">
    <div ref="container" class="micro-app-container" />
    <el-empty v-if="error" :description="uiText('子应用加载失败，请联系管理员')"><el-button @click="mount">{{ uiText('重试') }}</el-button></el-empty>
    <el-skeleton v-else-if="loading" :rows="8" animated />
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { findTrustedMicroApp, microFrontendsEnabled } from '@/microfrontends/registry'
import { mountTrustedMicroApp, type MountedMicroApp } from '@/microfrontends/runtime'
import { uiText } from '@/i18n/uiText'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const tenants = useTenantStore()
const container = ref<HTMLElement>()
const loading = ref(true)
const error = ref(false)
const app = findTrustedMicroApp(String(route.params.appKey))
let mounted: MountedMicroApp | undefined
let generation = 0, active = true
function childRoute() {
  const base = app?.routeBase || ''
  return route.fullPath.startsWith(base) ? route.fullPath.slice(base.length) || '/' : '/'
}

async function unmount() {
  const previous = mounted
  mounted = undefined
  if (previous) await previous.unmount()
}

async function mount() {
  const owner = ++generation
  if (!container.value || !app || !microFrontendsEnabled() || !auth.user) {
    loading.value = false
    error.value = true
    return
  }
  loading.value = true
  error.value = false
  try {
    const instance = await mountTrustedMicroApp({
      app,
      container: container.value,
      route: childRoute(),
      identity: { userId: auth.user.id, permissions: auth.user.permissions || [], tenantId: tenants.currentId },
      onNavigate: path => void router.push(`${app.routeBase}${path === '/' ? '' : path}`),
    })
    if (!active || owner !== generation) { await instance.unmount(); return }
    mounted = instance
  } catch {
    if (active && owner === generation) error.value = true
  } finally {
    if (active && owner === generation) loading.value = false
  }
}

onMounted(() => { void mount() })
watch(() => route.fullPath, () => {
  if (mounted) window.dispatchEvent(new CustomEvent('admincore:micro-route', { detail: childRoute() }))
})
onBeforeUnmount(() => { active = false; generation++; void unmount() })
</script>

<style scoped>
.micro-app-shell { min-height: 60vh; width: 100%; }
.micro-app-container { min-height: 60vh; width: 100%; }
</style>
