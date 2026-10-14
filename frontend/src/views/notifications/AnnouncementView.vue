<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="heading"><h2>{{ uiText('通知公告') }}</h2><BaseButton v-if="manage && canUpdate" variant="primary" :disabled="saving" @click="edit()">{{ uiText('新增公告') }}</BaseButton></div></template>
      <p class="notice">{{ uiText('已发布公告面向所有已登录用户，新用户也可阅读；不计入个人通知未读数。') }}</p>
      <el-radio-group v-if="canManage" v-model="manage" :disabled="saving" @change="resetList">
        <el-radio-button :value="false">{{ uiText('已发布公告') }}</el-radio-button><el-radio-button :value="true">{{ uiText('公告管理') }}</el-radio-button>
      </el-radio-group>
      <el-form class="filters" inline @submit.prevent="resetList">
        <el-form-item :label="uiText('关键词')"><el-input v-model="keyword" clearable maxlength="200" /></el-form-item>
        <el-form-item v-if="manage" :label="uiText('状态')"><el-select v-model="status" class="status-filter"><el-option :label="uiText('全部')" value="" /><el-option v-for="value in states" :key="value" :label="label(value)" :value="value" /></el-select></el-form-item>
        <el-form-item><BaseButton :loading="loading" @click="resetList">{{ uiText('搜索') }}</BaseButton></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :action-width="manage ? 240 : 80" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }">
          <el-button link type="primary" :loading="detailLoadingId === row.id" @click="detail(row)">{{ uiText('详情') }}</el-button>
          <el-button v-if="manage && canUpdate && row.status !== 'published'" link type="primary" :disabled="saving" @click="edit(row)">{{ uiText('编辑') }}</el-button>
          <el-button v-if="manage && canPublish" link :type="row.status === 'published' ? 'danger' : 'primary'" :disabled="saving" @click="transition(row)">{{ uiText(row.status === 'published' ? '撤回公告' : '发布公告') }}</el-button>
        </template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="visible" :title="uiText(form.id ? '编辑公告' : '新增公告')" :before-close="guard.confirmDiscard" :loading="saving" :confirm-disabled="!canUpdate" @confirm="save">
      <div v-if="formError" ref="errorSummary" tabindex="-1"><el-alert :title="formError" type="error" :closable="false" /></div>
      <el-form label-position="top" :disabled="saving" @submit.prevent="save">
        <el-form-item :label="uiText('标题')" required><el-input v-model="form.title" maxlength="200" show-word-limit /></el-form-item>
        <el-form-item :label="uiText('公告正文')" required><el-input v-model="form.content" type="textarea" :rows="8" maxlength="20000" show-word-limit /></el-form-item>
      </el-form>
      <p class="notice">{{ uiText('保存为草稿后，需单独发布才能供全员阅读；已发布内容须先撤回才能编辑。') }}</p>
    </BaseDialog>
    <BaseDialog v-model="detailVisible" :title="selected?.title || uiText('公告详情')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="detailVisible = false">
      <p v-if="selected" class="notice">{{ label(selected.status) }} · {{ selected.published_at || selected.created_at }}</p>
      <div class="body-text">{{ selected?.content }}</div>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onScopeDispose, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AppLayout, BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { announcementsApi, type AnnouncementRow } from '@/api/announcements'
import { newIdempotencyKey } from '@/api'
import { uiText } from '@/i18n/uiText'

const auth = useAuthStore(), modules = useModuleStore()
const owner = auth.user?.id
const accessible = computed(() => auth.isAuthenticated && auth.user?.id === owner && !auth.user?.must_change_password && modules.enabled('notifications'))
const admin = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser))
const canManage = computed(() => accessible.value && admin.value && auth.can('announcement:read'))
const canUpdate = computed(() => canManage.value && auth.can('announcement:update'))
const canPublish = computed(() => canManage.value && auth.can('announcement:publish'))
const manage = ref(false), loading = ref(false), saving = ref(false), visible = ref(false), detailVisible = ref(false)
const rows = ref<AnnouncementRow[]>([]), selected = ref<AnnouncementRow>(), total = ref(0), page = ref(1), pageSize = ref(20), keyword = ref(''), status = ref(''), error = ref(''), formError = ref('')
const detailLoadingId = ref('')
useErrorSummary(formError)
const form = reactive({ id: '', title: '', content: '', version: 0 })
const states = ['draft', 'published', 'withdrawn'] as const
const label = (value: string) => uiText(({ draft: '草稿', published: '已发布', withdrawn: '已撤回' } as Record<string, string>)[value] || value)
const columns = computed(() => [{ prop: 'title', label: uiText('标题') }, { prop: 'status', label: uiText('状态'), width: 100, render: label }, { prop: 'published_at', label: uiText('发布时间'), width: 190 }])
const guard = useUnsavedChanges({ source: () => form, active: () => visible.value, busy: () => saving.value, canEdit: () => canUpdate.value,
  clear: () => { visible.value = false; Object.assign(form, { id: '', title: '', content: '', version: 0 }); formError.value = '' } })
let generation = 0, listRequest: AbortController | undefined, detailRequest: AbortController | undefined
let saveKey = '', saveBody = ''
async function load() {
  const current = ++generation; listRequest?.abort(); listRequest = new AbortController()
  if (!accessible.value || (manage.value && !canManage.value)) { loading.value = false; return }
  loading.value = true; error.value = ''; rows.value = []; total.value = 0
  try {
    const data = await announcementsApi.list(manage.value, { page: page.value, page_size: pageSize.value, search: keyword.value, ...(manage.value && status.value ? { status: status.value } : {}) }, listRequest.signal)
    if (current !== generation || !accessible.value || !guard.isSessionCurrent()) return
    rows.value = data.items; total.value = data.pagination.total
  } catch { if (current === generation && accessible.value && guard.isSessionCurrent()) error.value = uiText('公告加载失败，请重试') }
  finally { if (current === generation) loading.value = false }
}
function resetList() { detailGeneration++; detailRequest?.abort(); detailLoadingId.value = ''; selected.value = undefined; detailVisible.value = false; page.value = 1; void load() }
function changePage(value: number) { page.value = value; void load() }
function changeSize(value: number) { pageSize.value = value; resetList() }
function edit(row?: AnnouncementRow) {
  if (!canUpdate.value || saving.value) return
  Object.assign(form, row ? { id: row.id, title: row.title, content: row.content, version: row.version } : { id: '', title: '', content: '', version: 0 })
  saveKey = ''; saveBody = ''; formError.value = ''; visible.value = true
}
async function save() {
  if (saving.value || !visible.value || !guard.isCurrent()) return
  saving.value = true; formError.value = ''
  try {
    if (!form.title.trim() || !form.content.trim()) { formError.value = uiText('请填写公告标题和正文'); return }
    const data = { title: form.title.trim(), content: form.content.trim(), version: form.version }
    const body = JSON.stringify(data)
    if (body !== saveBody || !saveKey) { saveKey = newIdempotencyKey('announcement-save'); saveBody = body }
    await announcementsApi.save(form.id, data, saveKey)
    if (!guard.isCurrent()) return
    guard.markClean(); visible.value = false; ElMessage.success(uiText('保存成功')); await load()
  } catch (exception: any) {
    if (guard.isCurrent()) formError.value = uiText(exception?.response?.status === 409 ? '公告已变化，已保留输入，请重新打开编辑窗口' : '保存失败，已保留输入')
  } finally { saving.value = false }
}
async function detail(row: AnnouncementRow) {
  if (!accessible.value || (manage.value && !canManage.value)) return
  const current = ++detailGeneration; detailRequest?.abort(); detailRequest = new AbortController()
  detailLoadingId.value = row.id; selected.value = undefined; detailVisible.value = false
  try {
    const data = await announcementsApi.detail(row.id, manage.value, detailRequest.signal)
    if (current !== detailGeneration || !accessible.value || !guard.isSessionCurrent()) return
    selected.value = data; detailVisible.value = true
  } catch { if (current === detailGeneration && accessible.value && guard.isSessionCurrent()) error.value = uiText('公告详情加载失败，请重试') }
  finally { if (current === detailGeneration) detailLoadingId.value = '' }
}
let detailGeneration = 0
let ownsConfirmation = false
async function transition(row: AnnouncementRow) {
  if (saving.value || !canPublish.value) return
  saving.value = true
  try {
    const operation = row.status === 'published' ? 'withdraw' : 'publish'
    ownsConfirmation = true
    await ElMessageBox.confirm(uiText(operation === 'publish' ? '发布后所有已登录用户都能阅读，确定发布公告吗？' : '撤回后普通用户将无法阅读，确定撤回公告吗？'), uiText('提示'), { type: 'warning', confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), closeOnClickModal: false })
    ownsConfirmation = false
    if (!canPublish.value || !guard.isSessionCurrent()) return
    await announcementsApi.transition(row, operation)
    if (!canPublish.value || !guard.isSessionCurrent()) return
    ElMessage.success(uiText(operation === 'publish' ? '公告已发布' : '公告已撤回')); await load()
  } catch { /* Cancellation has no write; request errors already have a message. */ }
  finally { ownsConfirmation = false; saving.value = false }
}
function clearSensitive() {
  if (ownsConfirmation) ElMessageBox.close()
  generation++; detailGeneration++; listRequest?.abort(); detailRequest?.abort(); loading.value = false; detailLoadingId.value = ''; rows.value = []; selected.value = undefined; detailVisible.value = false; total.value = 0
}
watch(canPublish, allowed => { if (!allowed && ownsConfirmation) ElMessageBox.close() }, { flush: 'sync' })
watch([accessible, canManage], ([allowed, management]) => {
  clearSensitive(); if (!management) manage.value = false
  if (allowed) void load()
}, { flush: 'sync' })
onScopeDispose(clearSensitive)
onMounted(load)
</script>

<style scoped>
h2 { margin: 0; font-size: var(--font-size-lg); }
.heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--spacing-md); }
.notice { color: var(--color-text-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.filters { margin-top: var(--spacing-lg); }
.status-filter { width: 130px; }
.body-text { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
:deep(.action-buttons .el-button) { min-height: 44px; min-width: 44px; }
@media (max-width: 640px) { .filters :deep(.el-form-item) { display: flex; margin-right: 0; } }
</style>
