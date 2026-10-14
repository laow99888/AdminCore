import { toRaw, watch, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useNavigationStore } from '@/stores/navigation'

/** Retain explicitly selected filters/pages in memory only, never entire forms or API rows. */
export function usePageState(fields: Record<string, Ref<unknown> | Record<string, unknown>>) {
  const navigation = useNavigationStore()
  const path = useRoute().path
  const owner = navigation.generation(path)
  const previous = navigation.query(path)
  if (previous) {
    for (const [key, field] of Object.entries(fields)) {
      if (!(key in previous)) continue
      if ('value' in field) field.value = structuredClone(previous[key])
      else Object.assign(field, structuredClone(previous[key]))
    }
  }
  watch(() => Object.fromEntries(Object.entries(fields).map(([key, field]) =>
    [key, 'value' in field ? field.value : field])), value => {
    // Query fields are JSON-compatible primitives/objects; unwrap Vue proxies before cloning.
    navigation.remember(path, JSON.parse(JSON.stringify(toRaw(value))), owner)
  }, { deep: true, immediate: true, flush: 'sync' })
}
