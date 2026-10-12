<template>
  <div class="base-table">
    <!-- 表头操作栏 -->
    <div class="table-toolbar" v-if="showToolbar">
      <slot name="toolbar"></slot>
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
      v-bind="$attrs"
      @selection-change="handleSelectionChange"
    >
      <!-- 多选列 -->
      <el-table-column v-if="selectable" type="selection" width="50" />

      <!-- 序号列 -->
      <el-table-column v-if="showIndex" label="#" type="index" width="50" />

      <!-- 数据列 -->
      <el-table-column
        v-for="col in columns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :align="col.align || 'left'"
        :sortable="col.sortable || false"
        :show-overflow-tooltip="col.showOverflow !== false"
      >
        <template v-if="col.render" #default="{ row }">
          {{ col.render(row[col.prop], row) }}
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
            <slot name="actions" :row="row">
              <el-button link type="primary" size="small" @click="handleEdit(row)">{{ uiText("编辑") }}</el-button>
              <el-button link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
            </slot>
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

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref, defineEmits } from 'vue'
import { Inbox } from 'lucide-vue-next'
import type { TableInstance } from 'element-plus'

interface Column<T = any> {
  prop: string
  label: string
  width?: string | number
  align?: 'left' | 'center' | 'right'
  showOverflow?: boolean
  sortable?: boolean | 'custom'
  render?: (value: any, row: T) => string | number | void
}

interface Props<T = any> {
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
}

withDefaults(defineProps<Props>(), {
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
  'selection-change': [value: any[]]
  'edit': [row: any]
  'delete': [row: any]
}>()

const tableRef = ref<TableInstance>()
const selectedRows = ref<any[]>([])

// 暴露表格实例和选中行，父组件可调用 clearSelection 等方法
defineExpose({ tableRef, selectedRows })

const handlePageChange = (page: number) => {
  emit('update:currentPage', page)
}

const handlePageSizeChange = (size: number) => {
  emit('update:pageSize', size)
}

const handleSelectionChange = (rows: any[]) => {
  selectedRows.value = rows
  emit('selection-change', rows)
}

const handleEdit = (row: any) => {
  emit('edit', row)
}

const handleDelete = (row: any) => {
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

.table-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
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
</style>
