<template>
  <AppLayout>
    <div class="task-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("任务中心（异步任务执行记录）") }}</div>
            <div class="header-actions">
              <el-select v-model="statusFilter" clearable :placeholder="uiText('状态')" style="width: 130px" @change="handleFilterChange">
                <el-option v-for="(label, key) in STATUS_LABELS" :key="key" :label="label" :value="key" />
              </el-select>
              <BaseButton variant="ghost" @click="loadTasks">{{ uiText("刷新") }}</BaseButton>
            </div>
          </div>
        </template>

        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <el-button
              v-if="auth.can('task:cancel') && (row.status === 'pending' || (row.status === 'running' && row.execution?.semantics === 'resume_uncommitted_rows'))"
              link
              type="danger"
              size="small"
              :disabled="!!acting"
              :loading="acting === row.id"
              @click="handleCancel(row)"
            >{{ uiText("取消") }}</el-button>
            <el-button v-if="canResume(row)" link type="warning" size="small" :disabled="!!acting" :loading="acting === row.id" @click="handleResume(row)">{{ uiText('接续未提交行') }}</el-button>
            <el-button link type="primary" size="small" @click="showResult(row)">{{ uiText("结果") }}</el-button>
          </template>
        </BaseTable>
      </BaseCard>

      <!-- 任务结果详情 -->
      <BaseDialog v-model="resultVisible" :title="uiText('任务结果 — {p0}', { p0: currentTask?.name || '' })" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="resultVisible = false">
        <template v-if="currentTask">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item :label="uiText('状态')">{{ STATUS_LABELS[currentTask.status] || currentTask.status }}</el-descriptions-item>
            <el-descriptions-item :label="uiText('耗时')">{{ currentTask.duration != null ? `${currentTask.duration}s` : '—' }}</el-descriptions-item>
            <el-descriptions-item v-if="currentTask.request_id" :label="uiText('请求关联 ID')" :span="2"><span class="correlation-id">{{ currentTask.request_id }}</span></el-descriptions-item>
            <el-descriptions-item v-if="currentTask.execution" :label="uiText('执行次数')">{{ currentTask.execution.attempt }}</el-descriptions-item>
            <el-descriptions-item v-if="currentTask.execution?.policy?.soft_timeout" :label="uiText('软 / 硬超时')">{{ currentTask.execution.policy.soft_timeout }}s / {{ currentTask.execution.policy.hard_timeout }}s</el-descriptions-item>
          </el-descriptions>
          <pre v-if="currentTask.result" class="result-json">{{ JSON.stringify(currentTask.result, null, 2) }}</pre>
          <div v-if="currentTask.error" class="task-error">{{ currentTask.error }}</div>
        </template>
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { ref } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { tasksApi, type TaskRow } from '@/api'
import { useRealtimeUpdates } from '@/composables/useRealtimeUpdates'

const auth = useAuthStore()
const loading = ref(false)
const resultVisible = ref(false)
const currentTask = ref<TaskRow | null>(null)
const statusFilter = ref('')
const tableData = ref<TaskRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const acting = ref('')
const actionGuard = useUnsavedChanges({ source: () => null, busy: () => !!acting.value, clear: () => { acting.value = '' }, canEdit: () => auth.can('task:cancel') || auth.can('task:retry') })

usePageState({ statusFilter, currentPage, pageSize })
const STATUS_LABELS: Record<string, string> = {
  pending: uiText("等待执行"),
  running: uiText("执行中"),
  success: uiText("成功"),
  failed: uiText("失败"),
  cancelled: uiText("已取消"),
}
const TYPE_LABELS: Record<string, string> = {
  import: uiText("导入"),
  export: uiText("导出"),
  backup: uiText("备份"),
  cleanup: uiText("清理"),
  notification: uiText("通知"),
  other: uiText("其他"),
}

const tableColumns = [
  { prop: 'name', label: uiText("任务名称") },
  { prop: 'task_type', label: uiText("类型"), width: '90px', render: (v: string) => TYPE_LABELS[v] || v },
  { prop: 'status', label: uiText("状态"), width: '100px', render: (v: string) => STATUS_LABELS[v] || v },
  { prop: 'progress', label: uiText('进度'), width: '90px', render: (value: number) => `${Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0))}%` },
  { prop: 'creator_name', label: uiText("发起人"), width: '110px' },
  {
    prop: 'duration',
    label: uiText("耗时"),
    width: '90px',
    render: (v: any) => (v != null ? `${v}s` : '—'),
  },
  { prop: 'created_at', label: uiText("创建时间"), width: '180px' },
]

const loadTasks = async () => {
  const current = beginRead()
  loading.value = true
  try {
    const data = await tasksApi.list({
      page: currentPage.value,
      page_size: pageSize.value,
      ...(statusFilter.value ? { status: statusFilter.value } : {}),
    })
    if (current()) { tableData.value = data.items; total.value = data.pagination.total }
  } finally {
    if (current()) loading.value = false
  }
}

const handleFilterChange = () => {
  currentPage.value = 1
  loadTasks()
}

const canResume = (row: TaskRow) => !!row.execution?.can_resume && row.creator === auth.user?.id && auth.can('task:retry') && auth.can('data_io:import')
const handleCancel = async (row: TaskRow) => {
  if (acting.value || !auth.can('task:cancel')) return
  acting.value = row.id
  try {
    await ElMessageBox.confirm(uiText('取消后已提交的数据保留，后续导入行停止；确定继续吗？'), uiText('提示'), { type: 'warning' })
    if (!actionGuard.isCurrent() || !auth.can('task:cancel')) return
    const res = await tasksApi.cancel(row.id)
    if (actionGuard.isCurrent()) { ElMessage.success(res.data?.message || uiText('任务已取消')); await loadTasks() }
  } catch (error) { if (error !== 'cancel' && error !== 'close' && actionGuard.isCurrent()) ElMessage.error(uiText('任务操作未确认，请刷新检查状态')) }
  finally { if (acting.value === row.id) acting.value = '' }
}
const handleResume = async (row: TaskRow) => {
  if (acting.value || !canResume(row)) return
  acting.value = row.id
  try {
    await ElMessageBox.confirm(uiText('接续将跳过已提交的行和已记录的校验错误，仅执行剩余行；确定继续吗？'), uiText('提示'), { type: 'warning' })
    if (!actionGuard.isCurrent() || !canResume(row)) return
    await tasksApi.resume(row.id)
    if (actionGuard.isCurrent()) { ElMessage.success(uiText('已登记接续未提交行')); await loadTasks() }
  } catch (error) { if (error !== 'cancel' && error !== 'close' && actionGuard.isCurrent()) ElMessage.error(uiText('任务操作未确认，请刷新检查状态')) }
  finally { if (acting.value === row.id) acting.value = '' }
}

const showResult = (row: TaskRow) => {
  currentTask.value = row
  resultVisible.value = true
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadTasks()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadTasks()
}

const beginRead = useRealtimeUpdates('tasks', loadTasks, () => { tableData.value = []; total.value = 0; loading.value = false; currentTask.value = null; resultVisible.value = false })
loadTasks()
</script>

<style scoped>
.correlation-id { overflow-wrap: anywhere; word-break: break-all; }
.task-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.result-json {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  max-height: 300px;
  overflow: auto;
}

.task-error {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  color: var(--color-error);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

@media (max-width: 768px) {
  .card-header-row { flex-direction: column; align-items: stretch; gap: var(--spacing-sm); }
  .card-header-title { white-space: normal; overflow-wrap: anywhere; }
  .header-actions { justify-content: flex-end; }
}
</style>
