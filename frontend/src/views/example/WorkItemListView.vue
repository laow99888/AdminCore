<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="header"><h2>{{ uiText('示例工单') }}</h2><BaseButton v-if="auth.can('example:create')" variant="primary" :disabled="busy" @click="edit()">{{ uiText('新增工单') }}</BaseButton></div></template>
      <div class="filters">
        <el-input v-model="search" :aria-label="uiText('搜索工单标题')" :placeholder="uiText('搜索工单标题')" maxlength="120" clearable @keyup.enter="searchRows" />
        <el-select v-model="status" :aria-label="uiText('工单状态')" clearable :placeholder="uiText('全部状态')" @change="searchRows"><el-option :label="uiText('待处理')" value="open" /><el-option :label="uiText('已完成')" value="done" /></el-select>
        <BaseButton :disabled="loading || busy" @click="searchRows">{{ uiText('搜索') }}</BaseButton><BaseButton :disabled="loading || busy" @click="loadRows">{{ uiText('刷新') }}</BaseButton>
      </div>
      <el-alert v-if="loadError" :title="uiText('列表加载失败，请刷新重试')" type="error" :closable="false" />
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :action-width="160" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }"><el-button link :disabled="busy" @click="inspect(row)">{{ uiText('详情') }}</el-button><el-button v-if="auth.can('example:update')" link type="primary" :disabled="busy" @click="edit(row)">{{ uiText('编辑') }}</el-button><el-button v-if="auth.can('example:delete')" link type="danger" :disabled="busy" @click="remove(row)">{{ uiText('删除') }}</el-button></template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="editOpen" :title="uiText(form.id ? '编辑工单' : '新增工单')" width="600px" :loading="formBusy" :confirm-disabled="conflict.active.value" :before-close="formGuard.confirmDiscard" :confirm-text="uiText('保存')" @confirm="save">
      <p v-if="formError" role="alert" class="form-error">{{ formError }}</p>
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="saving || !formGuard.isCurrent()" :version="form.version" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <el-form :model="form" :disabled="formBusy" label-position="top" @submit.prevent="save">
        <el-form-item :label="uiText('工单标题')" required><el-input v-model="form.title" :aria-label="uiText('工单标题')" maxlength="120" /></el-form-item>
        <el-form-item :label="uiText('工单说明')"><el-input v-model="form.notes" :aria-label="uiText('工单说明')" type="textarea" :rows="4" maxlength="2000" /></el-form-item>
        <el-form-item :label="uiText('工单状态')"><el-select v-model="form.status" :aria-label="uiText('工单状态')"><el-option :label="uiText('待处理')" value="open" /><el-option :label="uiText('已完成')" value="done" /></el-select></el-form-item>
        <el-form-item :label="uiText('优先级')"><el-select v-model="form.priority" :aria-label="uiText('优先级')"><el-option :label="uiText('普通')" value="normal" /><el-option :label="uiText('高')" value="high" /></el-select></el-form-item>
      </el-form>
    </BaseDialog>
    <BaseDialog v-model="detailOpen" :title="uiText('工单详情')" width="600px" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="detailOpen = false" @close="selected = null">
      <dl v-if="selected"><dt>{{ uiText('工单标题') }}</dt><dd>{{ selected.title }}</dd><dt>{{ uiText('工单说明') }}</dt><dd class="notes">{{ selected.notes || uiText('无') }}</dd><dt>{{ uiText('版本') }}</dt><dd>{{ selected.version }}</dd></dl>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { BaseButton, BaseCard, BaseDialog, BaseTable } from '@/components'
import AppLayout from '@/components/layout/AppLayout.vue'
import { exampleApi, newIdempotencyKey, type ExampleWorkItem, type ExampleWrite } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { useEditConflict } from '@/composables/useEditConflict'
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { exampleMessages } from '@/i18n/exampleMessages'

registerUiMessages(exampleMessages)
const auth = useAuthStore(), modules = useModuleStore()
const rows = ref<ExampleWorkItem[]>([]), total = ref(0), page = ref(1), pageSize = ref(10)
const search = ref(''), appliedSearch = ref(''), status = ref(''), loading = ref(false), loadError = ref(false)
const editOpen = ref(false), detailOpen = ref(false), selected = ref<ExampleWorkItem | null>(null)
const saving = ref(false), removing = ref(false)
const formBusy = computed(() => saving.value || conflict.loading.value), busy = computed(() => formBusy.value || removing.value)
const initial = (): ExampleWrite & { id: string } => ({ id: '', title: '', notes: '', status: 'open', priority: 'normal', version: 0 })
const form = reactive(initial()), formError = ref('')
let key = '', submitted = '', generation = 0, alive = true
const canRead = () => auth.can('example:read') && modules.enabled('example')
const canWrite = () => canRead() && auth.can(form.id ? 'example:update' : 'example:create')
const formGuard = useUnsavedChanges({ source: () => form, active: () => editOpen.value, busy: () => formBusy.value,
  canEdit: canWrite, clear: () => { editOpen.value = false; Object.assign(form, initial()); formError.value = ''; key = ''; submitted = '' } })
const conflict = useEditConflict<ExampleWorkItem>({ identifier: () => editOpen.value ? form.id : '', current: () => formGuard.isCurrent(), fetch: exampleApi.detail,
  apply: row => { Object.assign(form, { title: row.title, notes: row.notes, status: row.status, priority: row.priority, version: row.version }); formError.value = ''; key = newIdempotencyKey('example'); submitted = ''; formGuard.markClean() } })
const conflictRows = computed(() => {
  const server = conflict.latest.value
  if (!server) return []
  return [
    { label: uiText('工单标题'), local: form.title, server: server.title },
    { label: uiText('工单说明'), local: form.notes, server: server.notes },
    { label: uiText('工单状态'), local: uiText(form.status === 'open' ? '待处理' : '已完成'), server: uiText(server.status === 'open' ? '待处理' : '已完成') },
    { label: uiText('优先级'), local: uiText(form.priority === 'high' ? '高' : '普通'), server: uiText(server.priority === 'high' ? '高' : '普通') },
  ]
})
const actionGuard = useUnsavedChanges({ source: () => null, busy: () => removing.value,
  canEdit: () => canRead() && auth.can('example:delete'), clear: () => {} })
useErrorSummary(formError)
const columns = computed(() => [
  { prop: 'title', label: uiText('工单标题'), width: 280 },
  { prop: 'status', label: uiText('工单状态'), width: 110, render: (value: string) => uiText(value === 'open' ? '待处理' : '已完成') },
  { prop: 'priority', label: uiText('优先级'), width: 90, render: (value: string) => uiText(value === 'high' ? '高' : '普通') },
  { prop: 'creator_name', label: uiText('创建者'), width: 140 }, { prop: 'version', label: uiText('版本'), width: 80 },
])
async function loadRows() {
  const current = ++generation; rows.value = []; total.value = 0; loadError.value = false
  if (!canRead()) return
  loading.value = true
  try { const data = await exampleApi.list({ page: page.value, page_size: pageSize.value, search: appliedSearch.value, status: status.value || undefined }); if (alive && current === generation && canRead()) { rows.value = data.items; total.value = data.pagination.total } }
  catch { if (alive && current === generation && canRead()) loadError.value = true }
  finally { if (alive && current === generation) loading.value = false }
}
function searchRows() { page.value = 1; appliedSearch.value = search.value.trim(); void loadRows() }
function changePage(value: number) { page.value = value; void loadRows() }
function changeSize(value: number) { page.value = 1; pageSize.value = value; void loadRows() }
function edit(row?: ExampleWorkItem) {
  if (busy.value || !canRead() || !auth.can(row ? 'example:update' : 'example:create')) return
  Object.assign(form, row ? { id: row.id, title: row.title, notes: row.notes, status: row.status, priority: row.priority, version: row.version } : initial())
  formError.value = ''; conflict.reset(); key = newIdempotencyKey('example'); submitted = ''; editOpen.value = true
}
function inspect(row: ExampleWorkItem) { if (canRead()) { selected.value = { ...row }; detailOpen.value = true } }
async function save() {
  if (busy.value || conflict.active.value || !formGuard.isCurrent()) return
  formError.value = ''
  if (!form.title.trim()) { formError.value = uiText('请填写工单标题'); return }
  const { id, ...data } = form, payload = { ...data, title: data.title.trim() }
  const digest = JSON.stringify(payload)
  if (submitted && submitted !== digest) key = newIdempotencyKey('example')
  submitted = digest; saving.value = true
  try { await exampleApi.save(id, payload, key); if (!formGuard.isCurrent()) return; formGuard.markClean(); editOpen.value = false; ElMessage.success(uiText('保存成功')); await loadRows() }
  catch (error: any) { if (!formGuard.isCurrent()) return; if (error.response?.status === 409 && form.id) conflict.mark(); else formError.value = uiText('保存失败，输入已保留；请检查字段或刷新选项后重试') }
  finally { saving.value = false }
}
async function remove(row: ExampleWorkItem) {
  if (busy.value || !actionGuard.isCurrent()) return
  removing.value = true
  try { await ElMessageBox.confirm(uiText('确定删除此工单？此操作不可恢复。'), uiText('提示'), { type: 'warning' }); if (!actionGuard.isCurrent()) return; await exampleApi.remove(row.id, row.version); if (!actionGuard.isCurrent()) return; if (rows.value.length === 1 && page.value > 1) page.value--; await loadRows() }
  catch (error: any) { if (actionGuard.isCurrent() && error !== 'cancel' && error !== 'close') ElMessage.warning(uiText('删除未确认，请刷新检查版本和状态')) }
  finally { removing.value = false }
}
watch(() => [auth.user?.id, auth.can('example:read'), modules.enabled('example')], () => { generation++; rows.value = []; total.value = 0; selected.value = null; detailOpen.value = false; if (canRead()) void loadRows() })
onBeforeUnmount(() => { alive = false; generation++; rows.value = []; selected.value = null })
void loadRows()
</script>

<style scoped>
.header, .filters { display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
.header { justify-content: space-between; }
h2 { margin: 0; font-size: var(--font-size-lg); }
.filters { margin-bottom: var(--spacing-md); }
.filters :deep(.el-input) { max-width: 320px; }
.filters :deep(.el-select) { width: 160px; }
.form-error { color: var(--el-color-danger); overflow-wrap: anywhere; }
dt { color: var(--color-text-secondary); }
dd { margin: var(--spacing-xs) 0 var(--spacing-md); overflow-wrap: anywhere; }
.notes { white-space: pre-wrap; }
@media (max-width: 640px) { .filters :deep(.el-input) { flex-basis: 100%; max-width: 100%; } }
</style>
