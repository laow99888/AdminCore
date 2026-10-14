import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

export interface NavigationTab { path: string; title: string }

export const useNavigationStore = defineStore('navigation', () => {
  const tabs = ref<NavigationTab[]>([])
  const epoch = ref(0)
  // Only whitelisted query fields are recorded; rows, forms and credentials stay out.
  const queries = new Map<string, Record<string, unknown>>()
  const generations = new Map<string, number>()

  function forget(path: string) {
    queries.delete(path)
    generations.set(path, (generations.get(path) || 0) + 1)
  }
  function clear() {
    tabs.value = []
    queries.clear()
    generations.clear()
    epoch.value++
  }
  function ensure(route: Pick<RouteLocationNormalizedLoaded, 'path' | 'meta'>) {
    if (!route.meta.requiresAuth || route.path === '/change-password') return
    if (!tabs.value.length) tabs.value.push({ path: '/', title: '仪表盘' })
    if (!tabs.value.some(tab => tab.path === route.path)) {
      tabs.value.push({ path: route.path, title: typeof route.meta.title === 'string' ? route.meta.title : route.path })
    }
  }
  function prune(allowed: (path: string) => boolean) {
    for (const tab of tabs.value) if (!allowed(tab.path)) forget(tab.path)
    tabs.value = tabs.value.filter(tab => allowed(tab.path))
  }
  async function close(path: string, router: Router) {
    const index = tabs.value.findIndex(tab => tab.path === path)
    if (index < 0 || path === '/') return
    if (router.currentRoute.value.path === path) {
      const target = tabs.value[index - 1]?.path || '/'
      const failure = await router.push(target)
      if (failure || router.currentRoute.value.path === path) return
    }
    tabs.value = tabs.value.filter(tab => tab.path !== path)
    forget(path)
  }
  async function closeOthers(path: string, router: Router) {
    if (!tabs.value.some(tab => tab.path === path)) return
    if (router.currentRoute.value.path !== path) {
      const failure = await router.push(path)
      if (failure || router.currentRoute.value.path !== path) return
    }
    for (const tab of tabs.value) if (tab.path !== '/' && tab.path !== path) forget(tab.path)
    tabs.value = tabs.value.filter(tab => tab.path === '/' || tab.path === path)
  }
  function query(path: string) { return queries.get(path) }
  function generation(path: string) { return `${epoch.value}:${generations.get(path) || 0}` }
  function remember(path: string, value: Record<string, unknown>, owner: string) {
    if (owner === generation(path)) queries.set(path, structuredClone(value))
  }
  return { tabs, epoch, ensure, prune, close, closeOthers, clear, query, generation, remember }
})
