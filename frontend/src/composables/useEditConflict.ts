import { onDeactivated, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'

/** 409 不更改草稿或版本；最新快照只在显式应用时载入。 */
export function useEditConflict<T>(options: {
  identifier: () => string
  current: () => boolean
  fetch: (id: string, signal: AbortSignal) => Promise<T>
  apply: (value: T) => void
}) {
  const auth = useAuthStore(), modules = useModuleStore()
  const active = ref(false), loading = ref(false), failed = ref(false), latest = shallowRef<T>()
  let generation = 0, controller: AbortController | undefined
  function reset() {
    generation++; controller?.abort(); controller = undefined
    active.value = false; loading.value = false; failed.value = false; latest.value = undefined
  }
  function mark() { reset(); active.value = true }
  async function inspect() {
    if (loading.value || !active.value || !options.identifier() || !options.current()) return
    const current = ++generation, identifier = options.identifier()
    controller?.abort(); controller = new AbortController()
    loading.value = true; failed.value = false; latest.value = undefined
    try {
      const value = await options.fetch(identifier, controller.signal)
      if (current === generation && identifier === options.identifier() && options.current()) latest.value = value
    } catch { if (current === generation && options.current()) failed.value = true }
    finally { if (current === generation) loading.value = false }
  }
  function applyLatest() {
    if (!latest.value || loading.value || !options.current()) return
    const value = latest.value
    reset(); options.apply(value)
  }
  watch([() => auth.user?.id, () => auth.token, () => JSON.stringify(auth.user?.permissions),
    () => JSON.stringify(modules.config), options.identifier], reset, { flush: 'sync' })
  onDeactivated(reset); onScopeDispose(reset)
  return { active, loading, failed, latest, reset, mark, inspect, applyLatest }
}
