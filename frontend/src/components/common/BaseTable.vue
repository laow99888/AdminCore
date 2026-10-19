<template>
  <div class="base-table" :class="`density-${effectiveDensity}`" :data-table-density="effectiveDensity">
    <!-- 表头操作栏 -->
    <div class="table-toolbar" v-if="showToolbar || preferenceKey">
      <slot v-if="showToolbar" name="toolbar"></slot>
      <TableColumnSettings v-if="preferenceKey" class="column-settings-trigger" :preference-key="preferenceKey" :columns="columns" @change="columnLayout = $event" />
    </div>

    <!-- 表格 -->
    <el-table
      ref="tableRef"
      :data="data"
      :columns="columns"
      v-loading="loading"
      style="width: 100%"
      stripe
      highlight-current-row
      :size="size ?? (tablePreferences.density === 'compact' ? 'small' : 'default')"
      v-bind="$attrs"
      @selection-change="handleSelectionChange"
    >
      <!-- 多选列 -->
      <el-table-column v-if="selectable" type="selection" width="50" />

      <!-- 序号列 -->
      <el-table-column v-if="showIndex" label="#" type="index" width="50" />

      <!-- 数据列 -->
      <el-table-column
        v-for="col in displayedColumns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :fixed="col.fixed"
        :align="col.align || 'left'"
        :sortable="col.sortable || false"
        :show-overflow-tooltip="col.showOverflow !== false"
      >
        <template v-if="col.render || col.format === 'datetime' || ['created_at', 'updated_at'].includes(col.prop)" #default="{ row }">
          {{ formatCell(col, row) }}
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column
        v-if="showActions"
        :label="uiText('操作')"
        :width="actionWidth"
        align="right"
        fixed="right"
      >
        <template #default="{ row }">
          <div class="action-buttons">
            <slot v-if="$slots.actions" name="actions" :row="row" />
            <template v-else>
              <el-button link type="primary" size="small" @click="handleEdit(row)">{{ uiText("编辑") }}</el-button>
              <el-button link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
            </template>
          </div>
        </template>
      </el-table-column>

      <!-- 空状态 -->
      <template #empty>
        <div class="table-empty">
          <Inbox :size="44" :stroke-width="1.25" class="empty-icon-svg" />
          <div class="empty-text">{{ uiText("暂无数据") }}</div>
        </div>
      </template>
    </el-table>

    <!-- 分页 -->
    <div class="table-pagination" v-if="showPagination && total > 0">
      <el-pagination
        :current-page="currentPage"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts" generic="T extends object">
import { uiText } from "@/i18n/uiText"

import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { Inbox } from 'lucide-vue-next'
import type { TableInstance } from 'element-plus'
import { useTablePreferencesStore } from '@/stores/tablePreferences'
import TableColumnSettings from './TableColumnSettings.vue'
import { normalizeColumns, type ColumnPin, type ColumnPreference } from '@/composables/useColumnPreferences'
import dayjs from 'dayjs'

type RenderCell<T> = { bivarianceHack(value: unknown, row: T): string | number | void }['bivarianceHack']

interface Column<T = unknown> {
  format?: 'datetime'
  prop: string
  label: string
  width?: string | number
  align?: 'left' | 'center' | 'right'
  showOverflow?: boolean
  sortable?: boolean | 'custom'
  fixed?: ColumnPin
  render?: RenderCell<T>
}

interface Props<T = unknown> {
  data: T[]
  columns: Column<T>[]
  loading?: boolean
  total?: number
  currentPage?: number
  pageSize?: number
  selectable?: boolean
  showIndex?: boolean
  showActions?: boolean
  showToolbar?: boolean
  showPagination?: boolean
  actionWidth?: string | number
  size?: 'small' | 'default' | 'large'
  preferenceKey?: string
  selectionIds?: string[]
}

const props = withDefaults(defineProps<Props<T>>(), {
  loading: false,
  total: 0,
  currentPage: 1,
  pageSize: 10,
  selectable: false,
  showIndex: true,
  showActions: true,
  showToolbar: false,
  showPagination: true,
  actionWidth: 150,
})

const emit = defineEmits<{
  'update:currentPage': [value: number]
  'update:pageSize': [value: number]
  'selection-change': [value: T[]]
  'edit': [row: T]
  'delete': [row: T]
}>()

defineSlots<{ actions(props: { row: T }): unknown; toolbar(): unknown }>()

const tableRef = ref<TableInstance>()
const columnLayout = ref<ColumnPreference[]>([])
const displayedColumns = computed(() => {
  if (!props.preferenceKey) return props.columns
  const known = new Map(props.columns.map(column => [column.prop, column]))
  return normalizeColumns(columnLayout.value, props.columns).filter(item => item.visible)
    .map(item => ({ ...known.get(item.prop)!, fixed: item.fixed }))
})
const tablePreferences = useTablePreferencesStore()
const effectiveDensity = computed(() => props.size ? (props.size === 'small' ? 'compact' : 'comfortable') : tablePreferences.density)
const selectedRows = shallowRef<T[]>([])
let syncingSelection = false, selectionGeneration = 0
watch(() => [props.data, props.selectionIds], async () => {
  if (!props.selectionIds) return
  const current = ++selectionGeneration
  syncingSelection = true
  await nextTick()
  if (current !== selectionGeneration) return
  tableRef.value?.clearSelection()
  const ids = new Set(props.selectionIds)
  for (const row of props.data) if (ids.has(String(Reflect.get(row, 'id')))) tableRef.value?.toggleRowSelection(row, true)
  await nextTick()
  if (current === selectionGeneration) syncingSelection = false
}, { immediate: true })
const cellValue = (row: unknown, prop: string): unknown => row !== null && typeof row === 'object' ? Reflect.get(row, prop) : undefined

function formatCell(col: Column<T>, row: T) {
  const value = cellValue(row, col.prop)
  if (col.render) return col.render(value, row)
  if ((col.format === 'datetime' || ['created_at', 'updated_at'].includes(col.prop)) &&
      typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && dayjs(value).isValid()) {
    return dayjs(value).format('YYYY-MM-DD HH:mm')
  }
  return value
}

// 暴露表格实例和选中行，父组件可调用 clearSelection 等方法
defineExpose({ tableRef, selectedRows })

const handlePageChange = (page: number) => {
  emit('update:currentPage', page)
}

const handlePageSizeChange = (size: number) => {
  emit('update:pageSize', size)
}

const handleSelectionChange = (rows: T[]) => {
  selectedRows.value = rows
  if (syncingSelection) return
  emit('selection-change', rows)
}

const handleEdit = (row: T) => {
  emit('edit', row)
}

const handleDelete = (row: T) => {
  emit('delete', row)
}
</script>

<style scoped>
.base-table {
  width: 100%;
  background-color: var(--color-bg-card);
  border-radius: var(--radius-xl);
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.table-toolbar {
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}
.column-settings-trigger { margin-left: auto; }

.table-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
}

.table-pagination :deep(.el-pagination) {
  max-width: 100%;
  flex-wrap: wrap;
  justify-content: flex-end;
  row-gap: var(--spacing-sm);
}

@media (max-width: 768px) {
  .table-pagination { padding: var(--spacing-sm); justify-content: center; }
  .table-pagination :deep(.el-pagination) { justify-content: center; }
}

.action-buttons {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
}

.table-empty {
  padding: var(--spacing-2xl);
  text-align: center;
  color: var(--color-text-tertiary);
}

.empty-icon-svg {
  color: var(--color-text-disabled);
  margin-bottom: var(--spacing-md);
}

.empty-text {
  font-size: var(--font-size-sm);
}

/* Element Plus 表格样式覆盖 */
:deep(.el-table) {
  background-color: var(--color-bg-card);
  border-color: var(--color-border);
}

:deep(.el-table__header th) {
  background-color: var(--color-bg-elevated);
  border-color: var(--color-border);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

:deep(.el-table__body tr:hover > td) {
  background-color: var(--color-bg-hover) !important;
}

:deep(.el-table__body td) {
  border-color: var(--color-border);
  color: var(--color-text-primary);
}

:deep(.el-table__cell) {
  padding: var(--spacing-md);
}

.density-compact :deep(.el-table__cell) {
  padding: var(--spacing-xs) var(--spacing-sm);
}

/* 密度只压缩内容留白，触屏操作目标仍保持可点击面积。 */
@media (pointer: coarse), (max-width: 768px) {
  .action-buttons :deep(button),
  .table-pagination :deep(button),
  .table-pagination :deep(.el-pager li) {
    min-width: 44px;
    min-height: 44px;
  }
}
</style>
