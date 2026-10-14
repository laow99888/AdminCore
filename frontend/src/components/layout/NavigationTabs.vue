<template>
  <nav class="navigation-shell" :aria-label="uiText('页面导航')">
    <div class="breadcrumb-row" :aria-label="uiText('面包屑')">
      <ol>
        <li><router-link to="/">{{ uiText('首页') }}</router-link></li>
        <li v-if="parent">
          <router-link v-if="parent.path" :to="parent.path">{{ uiText(parent.title) }}</router-link>
          <span v-else>{{ uiText(parent.title) }}</span>
        </li>
        <li v-if="route.path !== '/'" aria-current="page">{{ uiText(String(route.meta.title || route.path)) }}</li>
      </ol>
    </div>
    <div ref="tabStrip" class="tabs-row" :aria-label="uiText('已打开页面')">
      <div v-for="tab in navigation.tabs" :key="tab.path" class="tab-group" :class="{ active: tab.path === route.path }">
        <button type="button" class="navigation-tab" :aria-current="tab.path === route.path ? 'page' : undefined"
          :data-path="tab.path" @click="router.push(tab.path)" @contextmenu.prevent="openContext($event, tab.path)"
          @keydown.shift.f10.prevent="openContext($event, tab.path)">{{ uiText(tab.title) }}</button>
        <button v-if="tab.path !== '/'" type="button" class="close-tab" :aria-label="uiText('关闭页签 {p0}', { p0: uiText(tab.title) })"
          @click="navigation.close(tab.path, router)"><X :size="14" aria-hidden="true" /></button>
      </div>
    </div>
    <Teleport to="body">
      <div v-if="context" ref="contextElement" class="context-menu" :style="{ left: `${context.x}px`, top: `${context.y}px` }" @keydown.esc.prevent="dismiss(true)">
        <button type="button" @click="closeOthers">{{ uiText('关闭其他页签') }}</button>
      </div>
    </Teleport>
    <button class="tabs-actions" type="button" :aria-label="uiText('页签操作')" @click="openContext($event, route.path)">
      <Ellipsis :size="18" aria-hidden="true" />
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { X, Ellipsis } from 'lucide-vue-next'
import { uiText } from '@/i18n/uiText'
import { useNavigationStore } from '@/stores/navigation'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { canAccessPage } from '@/router/access'

const route = useRoute(), router = useRouter(), navigation = useNavigationStore()
const auth = useAuthStore(), modules = useModuleStore()
const tabStrip = ref<HTMLElement>(), contextElement = ref<HTMLElement>()
const context = ref<{ path: string; x: number; y: number; trigger: HTMLElement } | null>(null)
let active = true
const parent = computed(() => {
  const path = route.path
  if (path === '/files/recycle' && canAccessPage('/files', auth.user) && modules.pathEnabled('/files')) return { path: '/files', title: '文件管理' }
  if (path === '/tasks/schedules' && canAccessPage('/tasks', auth.user) && modules.pathEnabled('/tasks')) return { path: '/tasks', title: '任务中心' }
  if (path === '/notifications/announcements' && modules.pathEnabled('/notifications')) return { path: '/notifications', title: '通知中心' }
  if (path === '/notifications/templates' && modules.pathEnabled('/notifications')) return { path: '/notifications', title: '通知中心' }
  if (path === '/organization/posts' && canAccessPage('/organization', auth.user)) return { path: '/organization', title: '组织与数据权限' }
  if (path.startsWith('/system/')) return { path: '', title: '系统管理' }
  return null
})
async function sync() {
  if (!active) return
  navigation.ensure(route)
  await nextTick()
  tabStrip.value?.querySelector<HTMLElement>('.tab-group.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}
async function openContext(event: MouseEvent | KeyboardEvent, path: string) {
  const trigger = event.currentTarget as HTMLElement, bounds = trigger.getBoundingClientRect()
  const x = event instanceof MouseEvent && event.type === 'contextmenu' ? event.clientX : bounds.left
  const y = event instanceof MouseEvent && event.type === 'contextmenu' ? event.clientY : bounds.bottom
  context.value = { path, x: Math.max(8, Math.min(x, innerWidth - 220)), y: Math.max(8, Math.min(y, innerHeight - 60)), trigger }
  await nextTick()
  contextElement.value?.querySelector('button')?.focus()
}
function dismiss(restoreFocus = false) {
  if (restoreFocus) context.value?.trigger.focus()
  context.value = null
}
async function closeOthers() {
  const path = context.value?.path
  dismiss(true)
  if (path) await navigation.closeOthers(path, router)
}
function outside(event: PointerEvent) { if (!contextElement.value?.contains(event.target as Node)) dismiss() }
function listen() { window.addEventListener('pointerdown', outside) }
function stop() { dismiss(); window.removeEventListener('pointerdown', outside) }
watch(() => route.fullPath, () => { dismiss(); void sync() }, { immediate: true })
onActivated(() => { active = true; listen(); void sync() })
onDeactivated(() => { active = false; stop() })
listen()
onBeforeUnmount(stop)
</script>

<style scoped>
.navigation-shell { position: relative; border-bottom: 1px solid var(--color-border); background: var(--color-bg-card); flex-shrink: 0; }
.breadcrumb-row { padding: 8px var(--spacing-xl) 4px; min-height: 28px; display: flex; align-items: center; }
.breadcrumb-row ol { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; line-height: 1.6; font-size: var(--font-size-sm); color: var(--color-text-secondary); overflow-wrap: anywhere; }
.breadcrumb-row li + li::before { content: '/'; margin-right: 8px; color: var(--color-text-secondary); }
.breadcrumb-row a { color: var(--color-text-primary); text-decoration: none; }
.breadcrumb-row a:hover { color: var(--color-primary-500); }
.tabs-row { display: flex; align-items: center; gap: 6px; overflow-x: auto; margin-right: 44px; padding: 0 8px 6px var(--spacing-xl); }
.tab-group { display: flex; flex-shrink: 0; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--color-text-secondary); }
.tab-group:hover, .tab-group.active { color: var(--color-primary-500); background: var(--color-bg-elevated); border-color: var(--color-border); }
.navigation-tab, .close-tab, .tabs-actions { border: 0; background: transparent; color: inherit; cursor: pointer; min-height: 44px; font: inherit; }
.navigation-tab { padding: 4px 10px; white-space: nowrap; font-size: var(--font-size-sm); }
.close-tab { display: grid; place-items: center; min-width: 44px; }
.tabs-actions { display: grid; place-items: center; position: absolute; bottom: 6px; right: 0; width: 44px; background: var(--color-bg-card); }
.navigation-tab:focus-visible, .close-tab:focus-visible, .tabs-actions:focus-visible { outline: 2px solid var(--color-primary-500); outline-offset: -2px; }
.context-menu { position: fixed; z-index: 1200; border: 1px solid var(--color-border); background: var(--color-bg-card); box-shadow: var(--shadow-lg); border-radius: var(--radius-md); }
.context-menu button { border: 0; background: transparent; color: var(--color-text-primary); min-height: 44px; padding: 8px 12px; cursor: pointer; font: inherit; }
@media (max-width: 768px) { .breadcrumb-row { padding-left: var(--spacing-lg); padding-right: var(--spacing-lg); } .tabs-row { padding-left: var(--spacing-lg); } }
</style>
