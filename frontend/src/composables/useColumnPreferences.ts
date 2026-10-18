import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'

export type ColumnPin = false | 'left' | 'right'
export interface ColumnPreference { prop: string; visible: boolean; fixed: ColumnPin }
export interface ConfigurableColumn { prop: string; label: string; fixed?: ColumnPin }
const PREFIX = 'admincore.table-columns.v1.'
const CHANGED = 'admincore:table-columns-changed'

export function normalizeColumns(value: unknown, columns: ConfigurableColumn[]): ColumnPreference[] {
  const current = new Map(columns.map(column => [column.prop, column]))
  const result: ColumnPreference[] = []
  if (Array.isArray(value) && value.length <= 256) for (const item of value) {
    if (!item || typeof item !== 'object' || !current.has(item.prop)) continue
    result.push({ prop: item.prop, visible: item.visible !== false,
      fixed: item.fixed === 'left' || item.fixed === 'right' ? item.fixed : false })
    current.delete(item.prop)
  }
  for (const column of current.values()) result.push({ prop: column.prop, visible: true, fixed: column.fixed ?? false })
  if (result.length && !result.some(column => column.visible)) result[0]!.visible = true
  return result
}

/** 只保存列标识/顺序/固定位置，绝不保存行、筛选值、凭据或角色权限。 */
export function useColumnPreferences(preferenceKey: Ref<string>, columns: Ref<ConfigurableColumn[]>, owner: Ref<string>) {
  const layout = ref<ColumnPreference[]>([])
  const persistenceUnavailable = ref(false)
  const storageKey = computed(() => preferenceKey.value && owner.value
    ? PREFIX + encodeURIComponent(JSON.stringify([owner.value, preferenceKey.value])) : '')
  function load() {
    let saved: unknown = null
    persistenceUnavailable.value = false
    try {
      const raw = storageKey.value ? localStorage.getItem(storageKey.value) : null
      if (raw && raw.length <= 65536) {
        const value = JSON.parse(raw)
        if (value?.version === 1) saved = value.columns
      }
    } catch { persistenceUnavailable.value = true }
    layout.value = normalizeColumns(saved, columns.value)
  }
  function save(next: ColumnPreference[]) {
    layout.value = normalizeColumns(next, columns.value)
    if (!storageKey.value) return
    try {
      localStorage.setItem(storageKey.value, JSON.stringify({ version: 1, columns: layout.value }))
      persistenceUnavailable.value = false
      window.dispatchEvent(new CustomEvent(CHANGED, { detail: storageKey.value }))
    } catch { persistenceUnavailable.value = true }
  }
  function reset() { save(normalizeColumns(null, columns.value)) }
  function changed(event: Event) {
    const key = event instanceof StorageEvent ? event.key : (event as CustomEvent).detail
    if (key === storageKey.value || key === null) load()
  }
  watch([storageKey, () => columns.value.map(column => [column.prop, column.fixed])], load, { immediate: true })
  window.addEventListener('storage', changed)
  window.addEventListener(CHANGED, changed)
  onScopeDispose(() => { window.removeEventListener('storage', changed); window.removeEventListener(CHANGED, changed) })
  return { layout, persistenceUnavailable, save, reset }
}
