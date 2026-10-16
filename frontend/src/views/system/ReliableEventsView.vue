<template>
  <AppLayout>
    <BaseCard>
      <template #header>
        <div class="event-header">
          <div>
            <strong>{{ uiText('可靠事件') }}</strong>
            <p class="event-hint">{{ uiText('失败事件会自动重试；修复原因后可手动重新派发。') }}</p>
          </div>
          <div class="event-filters">
            <el-select v-model="statusFilter" :aria-label="uiText('状态')" clearable :placeholder="uiText('状态')" @change="filterChanged">
              <el-option v-for="(label, key) in statusLabels" :key="key" :label="label" :value="key" />
            </el-select>
            <BaseButton variant="ghost" :disabled="loading" @click="loadEvents">{{ uiText('刷新') }}</BaseButton>
          </div>
        </div>
      </template>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon role="alert" />
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize"
        @update:currentPage="changePage" @update:pageSize="changePageSize">
        <template #actions="{ row }">
          <el-button link type="primary" :disabled="detailsLoading" @click="showDetails(row.id)">{{ uiText('详情') }}</el-button>
          <el-button v-if="row.status === 'failed'" link type="warning" :loading="retrying === row.id" :disabled="!!retrying"
            @click="retryEvent(row.id)">{{ uiText('重新派发') }}</el-button>
        </template>
      </BaseTable>
      <BaseDialog v-model="detailsVisible" :title="uiText('事件详情')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="detailsVisible = false">
        <el-descriptions v-if="currentEvent" :column="1" border>
          <el-descriptions-item :label="uiText('事件主题')">{{ currentEvent.topic }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('状态')">{{ statusLabels[currentEvent.status] }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('尝试次数')">{{ currentEvent.attempts }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('下次执行时间')">{{ currentEvent.available_at }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('投递时间')">{{ currentEvent.published_at || '—' }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('请求标识')"><span class="event-value">{{ currentEvent.request_id || '—' }}</span></el-descriptions-item>
          <el-descriptions-item :label="uiText('错误信息')"><span class="event-value">{{ currentEvent.last_error || '—' }}</span></el-descriptions-item>
        </el-descriptions>
      </BaseDialog>
    </BaseCard>
  </AppLayout>
</template>

<script setup lang="ts">
import { usePageState } from '@/composables/usePageState'
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { reliableEventsApi, type OutboxEventRow } from '@/api'
import { uiText } from '@/i18n/uiText'

const rows = ref<OutboxEventRow[]>([])
const loading = ref(false)
const loadError = ref('')
const retrying = ref('')
const detailsLoading = ref(false)
const detailsVisible = ref(false)
const currentEvent = ref<OutboxEventRow | null>(null)
const statusFilter = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
usePageState({ statusFilter, page, pageSize })
const statusLabels = { pending: uiText('等待执行'), processing: uiText('发送中'), failed: uiText('失败'), succeeded: uiText('已投递') }
const columns = [
  { prop: 'topic', label: uiText('事件主题'), minWidth: '180px' },
  { prop: 'status', label: uiText('状态'), width: '100px', render: (value: OutboxEventRow['status']) => statusLabels[value] || value },
  { prop: 'attempts', label: uiText('尝试次数'), width: '100px' },
  { prop: 'last_error', label: uiText('错误信息'), minWidth: '160px' },
  { prop: 'available_at', label: uiText('下次执行时间'), width: '200px' },
]
// 连续翻页/筛选时，旧请求不得覆盖最新列表。
let loadVersion = 0
async function loadEvents() {
  const version = ++loadVersion
  loading.value = true
  loadError.value = ''
  try {
    const result = await reliableEventsApi.list({ page: page.value, page_size: pageSize.value, ...(statusFilter.value ? { status: statusFilter.value } : {}) })
    if (version !== loadVersion) return
    rows.value = result.items
    total.value = result.pagination.total
  } catch {
    if (version !== loadVersion) return
    rows.value = []
    total.value = 0
    loadError.value = uiText('事件记录加载失败，请重试')
  } finally {
    if (version === loadVersion) loading.value = false
  }
}
function filterChanged() { page.value = 1; void loadEvents() }
function changePage(value: number) { page.value = value; void loadEvents() }
function changePageSize(value: number) { pageSize.value = value; filterChanged() }
async function showDetails(id: string) {
  if (detailsLoading.value) return
  detailsLoading.value = true
  try {
    currentEvent.value = await reliableEventsApi.detail(id)
    detailsVisible.value = true
  } catch { ElMessage.error(uiText('事件详情加载失败，请重试')) }
  finally { detailsLoading.value = false }
}
async function retryEvent(id: string) {
  if (retrying.value) return
  retrying.value = id
  try {
    try { await ElMessageBox.confirm(uiText('重新派发此失败事件？'), uiText('提示'), { type: 'warning' }) }
    catch { return }
    await reliableEventsApi.retry(id)
    ElMessage.success(uiText('已提交重试'))
    await loadEvents()
  } catch { ElMessage.error(uiText('重试提交失败，请刷新状态后重试')) }
  finally { retrying.value = '' }
}
void loadEvents()
</script>

<style scoped>
.event-header { display: flex; justify-content: space-between; gap: var(--spacing-md); flex-wrap: wrap; }
.event-hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); margin-top: var(--spacing-sm); }
.event-filters { display: flex; gap: var(--spacing-sm); align-items: center; }
.event-filters :deep(.el-select) { width: 140px; }
.event-value { overflow-wrap: anywhere; }
@media (max-width: 768px) { .event-filters { width: 100%; } .event-filters :deep(.el-select) { flex: 1; } }
</style>
