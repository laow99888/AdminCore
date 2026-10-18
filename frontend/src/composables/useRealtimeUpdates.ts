import { onMounted, onActivated, onDeactivated, onUnmounted, watch } from 'vue'
import { REALTIME_EVENT, type RealtimeTopics } from '@/utils/realtime'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { sessionIdentity } from '@/auth/sessionIdentity'

/** 列表只重新取数，不覆盖编辑草稿；轮询作为流断线/未启用时的回退。 */
export function useRealtimeUpdates(topic: keyof RealtimeTopics, refresh: () => Promise<void>, clear: () => void) {
  const auth = useAuthStore()
  const modules = useModuleStore()
  const allowed = () => !!auth.user && !auth.user.must_change_password && modules.enabled(topic) && (topic !== 'tasks' || auth.can('task:read'))
  let active = true
  let generation = 0
  let busy = false
  let signature = ''
  let timer: number | undefined
  let debounce: number | undefined
  const load = async () => {
    if (!active || busy || !allowed() || document.visibilityState === 'hidden' || navigator.onLine === false) return
    busy = true
    try { await refresh() } finally { busy = false }
  }
  const receive = (event: Event) => {
    const value = (event as CustomEvent<RealtimeTopics>).detail?.[topic]
    const next = JSON.stringify(value ?? null)
    if (next === signature) return
    signature = next
    window.clearTimeout(debounce)
    debounce = window.setTimeout(() => { void load().catch(() => undefined) }, 250)
  }
  const activate = () => {
    active = true
    window.clearInterval(timer)
    window.removeEventListener(REALTIME_EVENT, receive)
    window.addEventListener(REALTIME_EVENT, receive)
    timer = window.setInterval(() => { void load().catch(() => undefined) }, 60000)
  }
  const deactivate = () => {
    active = false; signature = ''; generation++
    window.clearInterval(timer); window.clearTimeout(debounce)
    window.removeEventListener(REALTIME_EVENT, receive)
  }
  watch([() => auth.user?.id, () => sessionIdentity(auth.token), () => auth.user?.must_change_password, () => JSON.stringify(auth.user?.permissions), () => modules.enabled(topic)], () => {
    generation++; signature = ''; clear()
    if (allowed()) void load().catch(() => undefined)
  })
  onMounted(activate); onActivated(activate); onDeactivated(deactivate); onUnmounted(deactivate)
  // 列表手动刷新、分页和 SSE 刷新共用代次，迟到响应不能覆盖新查询或新身份。
  return () => {
    const requestGeneration = ++generation
    return () => active && allowed() && requestGeneration === generation
  }
}
