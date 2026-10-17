<template>
  <AppLayout>
    <BaseCard>
      <template #header>
        <div class="recycle-header">
          <div>
            <strong>{{ uiText('文件回收站') }}</strong>
            <p class="recycle-hint">{{ policyText }}</p>
          </div>
          <div class="recycle-filters">
            <el-input v-model="search" :aria-label="uiText('搜索文件名')" :placeholder="uiText('搜索文件名')" clearable @keyup.enter="filterChanged" @clear="filterChanged" />
            <BaseButton variant="ghost" :disabled="loading || busy" @click="filterChanged">{{ uiText('搜索') }}</BaseButton>
            <BaseButton variant="ghost" :disabled="loading || busy" @click="loadFiles">{{ uiText('刷新') }}</BaseButton>
          </div>
        </div>
      </template>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" role="alert" />
      <div class="recycle-actions">
        <BaseButton v-if="auth.can('file:restore')" variant="primary" :disabled="!selected.length || busy || loading" @click="restore(selected)">{{ uiText('恢复所选') }}</BaseButton>
        <BaseButton v-if="auth.can('file:purge')" variant="ghost" :disabled="!selected.length || busy || loading" @click="previewPurge(selected)">{{ uiText('彻底删除所选') }}</BaseButton>
        <BaseButton variant="ghost" @click="router.push('/files')">{{ uiText('返回文件列表') }}</BaseButton>
      </div>
      <BaseTable :key="tableVersion" :data="rows" :columns="columns" :selectable="auth.can('file:restore') || auth.can('file:purge')"
        :show-actions="auth.can('file:restore') || auth.can('file:purge')"
        :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-index="false" :action-width="180"
        @selection-change="selected = $event" @update:currentPage="changePage" @update:pageSize="changePageSize">
        <template #actions="{ row }">
          <el-button v-if="auth.can('file:restore')" link type="primary" :disabled="busy || loading" @click="restore([row])">{{ uiText('恢复') }}</el-button>
          <el-button v-if="auth.can('file:purge')" link type="danger" :disabled="busy || loading" @click="previewPurge([row])">{{ uiText('彻底删除') }}</el-button>
        </template>
      </BaseTable>
      <BaseDialog v-model="purgeVisible" :title="uiText('确认彻底删除')" :loading="busy" :confirm-disabled="confirmation !== 'DELETE' || !!preview?.failed"
        :confirm-text="uiText('彻底删除')" @confirm="purge">
        <el-alert :title="uiText('此操作会永久删除文件，无法从回收站恢复')" type="warning" :closable="false" />
        <p>{{ uiText('本次将删除 {p0} 个文件，共 {p1} 字节', { p0: preview?.succeeded || 0, p1: previewBytes }) }}</p>
        <ul class="recycle-results">
          <li v-for="item in preview?.results" :key="item.id">{{ nameFor(item.id) }} — {{ item.status === 200 ? uiText('可删除') : item.message }}</li>
        </ul>
        <label for="purge-confirmation">{{ uiText('输入 DELETE 确认') }}</label>
        <el-input id="purge-confirmation" v-model="confirmation" autocomplete="off" :disabled="busy" />
      </BaseDialog>
      <BaseDialog v-model="resultVisible" :title="uiText('操作结果')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="resultVisible = false">
        <p>{{ uiText('成功 {p0} 项，失败 {p1} 项', { p0: result?.succeeded || 0, p1: result?.failed || 0 }) }}</p>
        <ul class="recycle-results">
          <li v-for="item in result?.results" :key="item.id">{{ nameFor(item.id) }} — {{ item.status === 200 ? uiText('已完成') : uiText(item.message) }}</li>
        </ul>
      </BaseDialog>
    </BaseCard>
  </AppLayout>
</template>

<script setup lang="ts">
import { notifyError } from "@/api/request"
import { usePageState } from '@/composables/usePageState'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { filesApi, type FileRow, type RecycleResult } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'

const auth = useAuthStore()
const router = useRouter()
const rows = ref<FileRow[]>([])
const selected = ref<FileRow[]>([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const search = ref('')
usePageState({ search, page, pageSize })
const loading = ref(false)
const busy = ref(false)
const loadError = ref('')
const tableVersion = ref(0)
const policy = ref<{ retention_days: number; cleanup_enabled: boolean } | null>(null)
const policyText = computed(() => policy.value
  ? policy.value.cleanup_enabled
    ? uiText('软删除保留 {p0} 天，过期文件由清理任务永久删除', { p0: policy.value.retention_days })
    : uiText('自动清理未启用；仍可手动恢复或彻底删除')
  : uiText('保留期以系统参数为准；已清理的文件无法恢复'))
const purgeVisible = ref(false)
const resultVisible = ref(false)
const confirmation = ref('')
const preview = ref<RecycleResult | null>(null)
const result = ref<RecycleResult | null>(null)
const pendingRows = ref<FileRow[]>([])
const previewBytes = computed(() => preview.value?.results.filter(item => item.status === 200).reduce((sum, item) => sum + (item.size || 0), 0) || 0)
const columns = [
  { prop: 'original_name', label: uiText('文件名'), width: '220px' },
  { prop: 'size_display', label: uiText('大小'), width: '100px' },
  { prop: 'uploader_name', label: uiText('上传者'), width: '120px' },
  { prop: 'deleted_at', label: uiText('删除时间'), width: '220px' },
]
let loadVersion = 0
const names = new Map<string, string>()
function nameFor(id: string) { return names.get(id) || uiText('文件') }
async function loadFiles() {
  const version = ++loadVersion
  loading.value = true
  loadError.value = ''
  selected.value = []
  try {
    const response = await filesApi.recycle({ page: page.value, page_size: pageSize.value, search: search.value })
    if (version !== loadVersion) return
    rows.value = response.items
    total.value = response.pagination.total
    tableVersion.value++
  } catch {
    if (version !== loadVersion) return
    rows.value = []
    total.value = 0
    loadError.value = uiText('回收站加载失败，请重试')
  } finally { if (version === loadVersion) loading.value = false }
}
function filterChanged() { page.value = 1; void loadFiles() }
function changePage(value: number) { page.value = value; void loadFiles() }
function changePageSize(value: number) { pageSize.value = value; filterChanged() }
function remember(items: FileRow[]) { items.forEach(item => names.set(item.id, item.original_name)) }
async function showResult(value: RecycleResult) {
  result.value = value
  if (value.succeeded) page.value = 1
  await loadFiles()
  resultVisible.value = true
}
async function restore(items: FileRow[]) {
  if (busy.value || !items.length) return
  const snapshot = items.map(item => ({ ...item }))
  remember(snapshot)
  busy.value = true
  try { await showResult(await filesApi.recycleAction('restore', snapshot)) }
  catch (error) { notifyError(error, uiText('操作失败，请刷新状态后重试')) }
  finally { busy.value = false }
}
async function previewPurge(items: FileRow[]) {
  if (busy.value || !items.length) return
  pendingRows.value = items.map(item => ({ ...item }))
  remember(pendingRows.value)
  busy.value = true
  try {
    preview.value = await filesApi.recycleAction('purge', pendingRows.value, true)
    confirmation.value = ''
    purgeVisible.value = true
  } catch (error) { notifyError(error, uiText('删除预览失败，请重试')) }
  finally { busy.value = false }
}
async function purge() {
  if (busy.value || confirmation.value !== 'DELETE' || preview.value?.failed || !pendingRows.value.length) return
  busy.value = true
  try {
    const response = await filesApi.recycleAction('purge', pendingRows.value, false, confirmation.value)
    purgeVisible.value = false
    await showResult(response)
  } catch (error) { notifyError(error, uiText('操作失败，请刷新状态后重试')) }
  finally { busy.value = false }
}
void loadFiles()
void filesApi.recyclePolicy().then(value => { policy.value = value }).catch(() => {})
</script>

<style scoped>
.recycle-header { display: flex; justify-content: space-between; gap: var(--spacing-md); flex-wrap: wrap; }
.recycle-hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); margin-top: var(--spacing-sm); }
.recycle-filters, .recycle-actions { display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
.recycle-filters :deep(.el-input) { width: 180px; }
.recycle-actions { margin-bottom: var(--spacing-md); }
.recycle-results { padding-left: var(--spacing-lg); overflow-wrap: anywhere; }
.recycle-results li { margin: var(--spacing-sm) 0; }
@media (max-width: 768px) { .recycle-filters { width: 100%; } .recycle-filters :deep(.el-input) { flex: 1; min-width: 100px; } }
</style>
