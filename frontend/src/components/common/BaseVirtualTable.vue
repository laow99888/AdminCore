<template>
  <div class="base-virtual-table" :data-table-density="preferences.density">
    <div ref="container" class="virtual-viewport" role="region" :aria-label="label" :aria-busy="loading" :style="{ height: `${safeHeight}px` }" tabindex="0" @keydown="navigate">
      <p v-if="invalid" role="alert" class="table-message">{{ uiText('虚拟表格数据不符合限制，请使用普通表格') }}</p>
      <el-table-v2 v-else-if="width > 0" ref="table" fixed :columns="virtualColumns" :data="loading ? [] : data" :width="width" :height="safeHeight" :row-height="rowHeight" :header-height="44" :cache="2" :row-key="rowKey" :row-props="rowProperties" :row-class="rowClass" :aria-label="label" :aria-rowcount="data.length + 1" :aria-colcount="virtualColumns.length" @scroll="scrolled">
        <template #cell="{ column, rowData, rowIndex }">
          <div v-if="column.key === '__actions'" class="virtual-actions"><slot name="actions" :row="rowData" /></div>
          <span v-else class="virtual-cell" :title="display(column.key as string, rowData, rowIndex)">{{ display(column.key as string, rowData, rowIndex) }}</span>
        </template>
        <template #empty><div role="status" class="table-message">{{ uiText(loading ? '加载中...' : '暂无数据') }}</div></template>
      </el-table-v2>
    </div>
    <p class="virtual-help">{{ uiText('仅显示已加载数据；聚焦表格后可用方向键、PageUp/PageDown、Home/End滚动') }}</p>
  </div>
</template>

<script setup lang="ts" generic="T extends object">
import { computed, nextTick, onActivated, onDeactivated, onMounted, onScopeDispose, ref, useSlots, watch } from 'vue'
import { ElTableV2, type TableV2Instance, type Column } from 'element-plus/es/components/table-v2/index'
import 'element-plus/es/components/table-v2/style/css'
import { uiText } from '@/i18n/uiText'
import { useTablePreferencesStore } from '@/stores/tablePreferences'

export interface VirtualColumn<T> { prop: string; label: string; width?: string | number; align?: 'left' | 'center' | 'right'; render?: { bivarianceHack(value: unknown, row: T): string | number | void }['bivarianceHack'] }
const props = withDefaults(defineProps<{ data: T[]; columns: VirtualColumn<T>[]; label: string; loading?: boolean; height?: number; rowKey?: string; showIndex?: boolean; contextKey?: string }>(),
  { loading: false, height: 420, rowKey: 'id', showIndex: true, contextKey: '' })
const preferences = useTablePreferencesStore(), slots = useSlots()
const container = ref<HTMLElement>(), table = ref<TableV2Instance>(), width = ref(0), top = ref(0)
const safeHeight = computed(() => Number.isFinite(props.height) ? Math.max(180, Math.min(1000, props.height)) : 420)
const rowHeight = computed(() => preferences.density === 'compact' ? 44 : 56)
const invalid = computed(() => {
  if (props.data.length > 10000 || !props.columns.length || props.columns.length > 30 || new Set(props.columns.map(col => col.prop)).size !== props.columns.length || props.columns.some(col => !col.prop || col.prop.startsWith('__'))) return true
  const keys = new Set<string>()
  for (const row of props.data) {
    if (row === null || typeof row !== 'object') return true
    const key: unknown = Reflect.get(row, props.rowKey)
    if ((typeof key !== 'string' && typeof key !== 'number') || key === '' || (typeof key === 'number' && !Number.isFinite(key)) || keys.has(String(key))) return true
    keys.add(String(key))
  }
  return false
})
const virtualColumns = computed<Column[]>(() => {
  const result: Column[] = props.columns.map(col => ({ key: col.prop, dataKey: col.prop, title: col.label,
    width: Math.max(80, Math.min(1000, Number.parseFloat(String(col.width)) || 200)), align: col.align }))
  if (props.showIndex) result.unshift({ key: '__index', title: '#', width: 64 })
  if (slots.actions) result.push({ key: '__actions', title: uiText('操作'), width: 160 })
  return result
})
function display(key: string, row: T, index: number) {
  if (key === '__index') return String(index + 1)
  const column = props.columns.find(col => col.prop === key)
  const cell: unknown = Reflect.get(row, key)
  const value = column?.render ? column.render(cell, row) : cell
  return typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number' ? String(value) : ''
}
const rowProperties = ({ rowIndex }: { rowIndex: number }) => ({ 'aria-rowindex': rowIndex + 2 })
const rowClass = ({ rowIndex }: { rowIndex: number }) => rowIndex % 2 ? 'virtual-striped' : ''
function scrolled({ scrollTop }: { scrollTop: number }) { top.value = scrollTop }
function reset() { top.value = 0; table.value?.scrollTo({ scrollTop: 0, scrollLeft: 0 }) }
function navigate(event: KeyboardEvent) {
  if (event.target !== container.value || props.loading || invalid.value || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  const page = Math.max(rowHeight.value, safeHeight.value - 44)
  const max = Math.max(0, props.data.length * rowHeight.value - page)
  const positions: Record<string, number> = { ArrowDown: top.value + rowHeight.value, ArrowUp: top.value - rowHeight.value, PageDown: top.value + page, PageUp: top.value - page, Home: 0, End: max }
  const target = positions[event.key]
  if (target === undefined) return
  event.preventDefault(); top.value = Math.max(0, Math.min(max, target)); table.value?.scrollToTop(top.value)
}
let observer: ResizeObserver | undefined
function observe() {
  if (!container.value) return
  width.value = Math.floor(container.value.clientWidth)
  observer?.disconnect()
  observer = new ResizeObserver(entries => { width.value = Math.floor(entries[0]?.contentRect.width || container.value?.clientWidth || 0) })
  observer.observe(container.value)
}
watch([() => props.data, () => props.columns, () => props.contextKey, () => props.loading, rowHeight], () => { void nextTick(reset) }, { deep: false })
onMounted(observe)
onActivated(observe)
onDeactivated(() => { observer?.disconnect(); reset() })
onScopeDispose(() => observer?.disconnect())
defineExpose({ reset })
</script>

<style scoped>
.base-virtual-table{min-width:0;max-width:100%;background:var(--color-bg-card);border:1px solid var(--color-border);border-radius:var(--radius-lg);overflow:hidden}
.virtual-viewport{min-width:0;width:100%;outline-offset:-3px}.virtual-viewport:focus-visible{outline:2px solid var(--color-primary)}
.virtual-cell{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;max-width:100%;display:block}
.virtual-actions{display:flex;gap:var(--spacing-xs)}.virtual-actions :deep(button){min-height:44px;min-width:44px}
.virtual-help{font-size:var(--font-size-xs);color:var(--color-text-secondary);padding:var(--spacing-sm);margin:0;overflow-wrap:anywhere;border-top:1px solid var(--color-border)}
.table-message{padding:var(--spacing-lg);color:var(--color-text-secondary)}
:deep(.el-table-v2){--el-table-border-color:var(--color-border);--el-table-bg-color:var(--color-bg-card);--el-table-tr-bg-color:var(--color-bg-card);--el-table-row-hover-bg-color:var(--color-bg-hover);color:var(--color-text-primary)}
:deep(.el-table-v2__header){background:var(--color-bg-elevated);font-weight:var(--font-weight-semibold)}
:deep(.el-table-v2__row.virtual-striped){background:var(--color-bg-elevated)}
</style>
