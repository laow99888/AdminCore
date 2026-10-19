<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="heading"><h2>{{ uiText('通知模板') }}</h2><BaseButton v-if="canUpdate" variant="primary" :disabled="saving" @click="edit()">{{ uiText('新增模板') }}</BaseButton></div></template>
      <p class="notice">{{ uiText('模板编辑生成新版本；已登记投递保持原版本。邮件仅发送至已验证邮箱。') }}</p>
      <el-tabs v-model="tab" @tab-change="resetList"><el-tab-pane :label="uiText('模板管理')" name="templates" /><el-tab-pane :label="uiText('投递记录')" name="deliveries" /></el-tabs>
      <el-form inline class="filters" @submit.prevent="resetList">
        <el-form-item v-if="tab === 'templates'" :label="uiText('关键词')"><el-input v-model="search" clearable maxlength="100" /></el-form-item>
        <el-form-item v-else :label="uiText('状态')"><el-select v-model="status" class="status-filter"><el-option :label="uiText('全部')" value="" /><el-option v-for="value in states" :key="value" :label="statusLabel(value)" :value="value" /></el-select></el-form-item>
        <el-form-item><BaseButton :loading="loading" @click="resetList">{{ uiText('刷新') }}</BaseButton></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <BaseTable v-if="tab === 'templates'" :data="templates" :columns="templateColumns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :action-width="220" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }"><el-button v-if="canUpdate" link type="primary" :disabled="saving" @click="edit(row)">{{ uiText('编辑') }}</el-button><el-button link type="primary" @click="history(row)">{{ uiText('版本记录') }}</el-button><el-button v-if="canSend" link type="primary" :disabled="saving || !row.enabled" @click="compose(row)">{{ uiText('发送通知') }}</el-button></template>
      </BaseTable>
      <BaseTable v-else :data="deliveries" :columns="deliveryColumns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :action-width="90" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }"><el-button v-if="canSend && row.status === 'failed'" link type="primary" :disabled="saving || row.attempts >= 5 || Date.parse(row.expires_at) <= Date.now()" @click="retry(row)">{{ uiText('重试') }}</el-button></template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="editorOpen" :title="uiText(form.id ? '编辑模板' : '新增模板')" :before-close="guard.confirmDiscard" :loading="saving || conflict.loading.value" :confirm-disabled="!canUpdate || conflict.active.value" @confirm="save">
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="saving || !guard.isCurrent()" :version="form.revision" :server-version="conflict.latest.value?.revision" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <el-form label-position="top" :disabled="saving" @submit.prevent="save">
        <el-form-item :label="uiText('模板编码')" required><el-input v-model="form.code" :disabled="!!form.id" maxlength="40" /></el-form-item>
        <el-form-item :label="uiText('模板名称')" required><el-input v-model="form.name" maxlength="100" /></el-form-item>
        <el-form-item :label="uiText('标题模板')" required><el-input v-model="form.subject" maxlength="200" /></el-form-item>
        <el-form-item :label="uiText('正文模板')"><el-input v-model="form.body" type="textarea" :rows="7" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item :label="uiText('变量名（逗号分隔）')"><el-input v-model="form.variablesText" maxlength="660" /></el-form-item>
        <p class="notice">{{ uiText('使用 ${name} 文本占位符，变量名需逐一声明；字面美元符写为 $$。不支持表达式或 HTML。') }}</p>
        <el-form-item :label="uiText('启用')"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
    </BaseDialog>
    <BaseDialog v-model="sendOpen" :title="uiText('发送通知')" :before-close="guard.confirmDiscard" :loading="saving" :confirm-text="uiText('确认发送')" :confirm-disabled="!canSend || !preview || previewing || !recipients.length || !channels.length" @confirm="send">
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      <p v-if="selected">{{ selected.name }} · {{ uiText('版本') }} {{ selected.revision }}</p>
      <el-form label-position="top" :disabled="saving" @submit.prevent="makePreview">
        <el-form-item v-for="key in selected?.current?.variables" :key="key" :label="key"><el-input v-model="values[key]" maxlength="2000" /></el-form-item>
        <el-form-item :label="uiText('收件人')"><PersonPicker v-model="picked" purpose="message" :disabled="saving || recipients.length >= 100" /><el-button :disabled="saving || !picked || recipients.length >= 100" @click="addRecipient">{{ uiText('添加收件人') }}</el-button></el-form-item>
        <div class="recipients"><el-tag v-for="person in recipients" :key="person.id" :closable="!saving" @close="removeRecipient(person.id)">{{ person.display_name }} ({{ person.username }})</el-tag></div>
        <el-form-item :label="uiText('投递渠道')"><el-checkbox-group v-model="channels" :disabled="saving || channelLoading"><el-checkbox value="inapp" :disabled="!available.inapp">{{ uiText('站内通知') }}</el-checkbox><el-checkbox value="email" :disabled="!available.email">{{ uiText('SMTP 邮件') }}</el-checkbox><el-checkbox value="webhook" :disabled="!available.webhook">Webhook</el-checkbox><el-checkbox value="sms" :disabled="!available.sms">{{ uiText('Twilio 短信') }}</el-checkbox></el-checkbox-group></el-form-item>
        <p class="notice">{{ uiText('外部渠道成功表示对端接收；短信结果不确定时终止，请核对供应商记录后处理。') }}</p>
        <p v-if="!available.email" class="notice">{{ uiText('邮件渠道未启用；请联系部署管理员配置。') }}</p>
        <el-button :loading="previewing" :disabled="saving || channelLoading" @click="makePreview">{{ uiText('预览通知') }}</el-button>
      </el-form>
      <section v-if="preview" class="preview" :aria-label="uiText('通知预览')"><h3>{{ preview.subject }}</h3><p>{{ preview.body }}</p></section>
      <p class="notice">{{ uiText('每位收件人、每个渠道独立记录；最多五次尝试。登记成功后请查看投递记录。') }}</p>
    </BaseDialog>
    <BaseDialog v-model="historyOpen" :title="uiText('版本记录')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="historyOpen = false">
      <el-skeleton v-if="historyLoading" :rows="5" animated />
      <div v-else-if="historyError" role="alert"><p>{{ uiText('版本加载失败，请重试') }}</p><el-button @click="loadHistory">{{ uiText('重试') }}</el-button></div>
      <template v-else><article v-for="version in versions" :key="version.id" class="preview"><h3>{{ uiText('版本') }} {{ version.number }} · {{ version.subject }}</h3><p>{{ version.body }}</p><p>{{ version.variables.join(', ') }}</p></article><p v-if="!versions.length">{{ uiText('暂无数据') }}</p><el-pagination v-if="historyTotal" :total="historyTotal" :current-page="historyPage" :page-size="10" :pager-count="5" layout="prev, pager, next" @current-change="historyPage = $event; loadHistory()" /></template>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { useEditConflict } from '@/composables/useEditConflict'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AppLayout, BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import PersonPicker from '@/components/common/PersonPicker.vue'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { messagesApi, type MessageTemplate, type MessageVersion, type MessageDelivery, type MessageChannel, type MessagePreview } from '@/api/messages'
import type { Person } from '@/api/personnel'
import { newIdempotencyKey } from '@/api'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { responseStatus } from '@/api/request'
import { notificationMessages } from '@/i18n/notificationMessages'

registerUiMessages(notificationMessages)

defineOptions({ name: 'MessageTemplatesView' })
const auth = useAuthStore(), modules = useModuleStore(), owner = auth.user?.id
const active = ref(true)
const canRead = computed(() => active.value && auth.isAuthenticated && !!auth.user && auth.user.id === owner && !auth.user.must_change_password && !!(auth.user.is_staff || auth.user.is_superuser) && modules.enabled('notifications') && auth.can('template:read'))
const canUpdate = computed(() => canRead.value && auth.can('template:update')), canSend = computed(() => canRead.value && auth.can('template:send'))
const tab = ref('templates'), search = ref(''), status = ref(''), page = ref(1), pageSize = ref(20), total = ref(0), loading = ref(false), saving = ref(false), error = ref(''), formError = ref('')
const templates = ref<MessageTemplate[]>([]), deliveries = ref<MessageDelivery[]>([])
const editorOpen = ref(false), sendOpen = ref(false), selected = ref<MessageTemplate>()
const blank = () => ({ id: '', code: '', name: '', subject: '', body: '', variablesText: '', enabled: true, revision: 0 })
const form = reactive(blank()), values = ref<Record<string, string>>({}), recipients = ref<Person[]>([]), picked = ref<Person | null>(null), channels = ref<MessageChannel[]>(['inapp'])
const available = ref({ inapp: false, email: false, webhook: false, sms: false }), channelLoading = ref(false), preview = ref<MessagePreview>(), previewing = ref(false)
const historyOpen = ref(false), historyId = ref(''), historyPage = ref(1), historyTotal = ref(0), historyLoading = ref(false), historyError = ref(false), versions = ref<MessageVersion[]>([])
let generation = 0, previewGeneration = 0, historyGeneration = 0, channelGeneration = 0
let listController: AbortController | undefined, previewController: AbortController | undefined, historyController: AbortController | undefined, channelController: AbortController | undefined
let sendBody = '', sendKey = '', ownsConfirmation = false
const states = ['pending', 'sending', 'succeeded', 'failed', 'terminated']
const statusLabel = (value: string) => uiText(({ pending: '待发送', sending: '发送中', succeeded: '成功', failed: '失败', terminated: '已终止' } as Record<string, string>)[value] || value)
const channelLabel = (value: string) => uiText(({ inapp: '站内通知', email: 'SMTP 邮件', webhook: 'Webhook', sms: 'Twilio 短信' } as Record<string, string>)[value] || value)
const templateColumns = computed(() => [{ prop: 'code', label: uiText('模板编码') }, { prop: 'name', label: uiText('模板名称') }, { prop: 'revision', label: uiText('版本'), width: 80 }, { prop: 'enabled', label: uiText('状态'), width: 100, render: (value: boolean) => uiText(value ? '已启用' : '未启用') }])
const deliveryColumns = computed(() => [{ prop: 'template_code', label: uiText('模板编码') }, { prop: 'version_number', label: uiText('版本'), width: 75 }, { prop: 'recipient', label: uiText('收件人标识'), width: 200 }, { prop: 'channel', label: uiText('投递渠道'), width: 110, render: channelLabel }, { prop: 'status', label: uiText('状态'), width: 85, render: statusLabel }, { prop: 'attempts', label: uiText('尝试次数'), width: 90 }, { prop: 'last_error', label: uiText('失败原因'), width: 180 }, { prop: 'request_id', label: uiText('请求关联 ID'), width: 200 }])
useErrorSummary(formError)
function invalidatePreview() { previewGeneration++; previewController?.abort(); preview.value = undefined; previewing.value = false }
function clearDraft() {
  if (ownsConfirmation) ElMessageBox.close()
  editorOpen.value = false; sendOpen.value = false; Object.assign(form, blank()); selected.value = undefined
  values.value = {}; recipients.value = []; picked.value = null; channels.value = ['inapp']; formError.value = ''; sendBody = ''; sendKey = ''
  invalidatePreview(); channelGeneration++; channelController?.abort(); available.value = { inapp: false, email: false, webhook: false, sms: false }; channelLoading.value = false
}
const guard = useUnsavedChanges({ source: () => editorOpen.value ? form : { values: values.value, recipients: recipients.value.map(person => person.id), channels: channels.value }, active: () => editorOpen.value || sendOpen.value, busy: () => saving.value || conflict.loading.value, canEdit: () => canRead.value && (editorOpen.value ? canUpdate.value : canSend.value), clear: clearDraft })
const conflict = useEditConflict<MessageTemplate>({ identifier: () => editorOpen.value ? form.id : '', current: () => guard.isCurrent(), fetch: messagesApi.detail,
  apply: row => { Object.assign(form, { id: row.id, code: row.code, name: row.name, enabled: row.enabled, revision: row.revision, subject: row.current?.subject ?? '', body: row.current?.body ?? '', variablesText: row.current?.variables.join(', ') ?? '' }); formError.value = ''; guard.markClean() } })
const conflictRows = computed(() => conflict.latest.value ? [
  { label: uiText('模板名称'), local: form.name, server: conflict.latest.value.name },
  { label: uiText('标题模板'), local: form.subject, server: conflict.latest.value.current?.subject ?? '—' },
  { label: uiText('正文模板'), local: form.body, server: conflict.latest.value.current?.body ?? '—' },
  { label: uiText('变量名（逗号分隔）'), local: form.variablesText, server: conflict.latest.value.current?.variables.join(', ') ?? '—' },
  { label: uiText('启用'), local: String(form.enabled), server: String(conflict.latest.value.enabled) },
] : [])
watch(values, invalidatePreview, { deep: true, flush: 'sync' })
async function load() {
  const current = ++generation; listController?.abort(); listController = new AbortController()
  templates.value = []; deliveries.value = []; total.value = 0; error.value = ''; loading.value = false
  if (!canRead.value) return
  loading.value = true
  try {
    if (tab.value === 'templates') {
      const data = await messagesApi.list({ page: page.value, page_size: pageSize.value, search: search.value }, listController.signal)
      if (current === generation && canRead.value && guard.isSessionCurrent()) { templates.value = data.items; total.value = data.pagination.total }
    } else {
      const data = await messagesApi.deliveries({ page: page.value, page_size: pageSize.value, status: status.value }, listController.signal)
      if (current === generation && canRead.value && guard.isSessionCurrent()) { deliveries.value = data.items; total.value = data.pagination.total }
    }
  } catch { if (current === generation && canRead.value && guard.isSessionCurrent()) error.value = uiText('通知配置加载失败，请重试') }
  finally { if (current === generation) loading.value = false }
}
function resetList() { page.value = 1; void load() }
function changePage(value: number) { page.value = value; void load() }
function changeSize(value: number) { pageSize.value = value; resetList() }
function edit(row?: MessageTemplate) {
  if (!canUpdate.value || saving.value) return
  conflict.reset(); clearDraft(); Object.assign(form, row ? { id: row.id, code: row.code, name: row.name, subject: row.current?.subject ?? '', body: row.current?.body ?? '', variablesText: row.current?.variables.join(', ') ?? '', enabled: row.enabled, revision: row.revision } : blank()); editorOpen.value = true
}
async function save() {
  if (saving.value || conflict.active.value || !editorOpen.value || !guard.isCurrent() || !canUpdate.value) return
  const variables = form.variablesText.split(',').map(value => value.trim()).filter(Boolean)
  if (!/^[a-z][a-z0-9_-]{0,39}$/.test(form.code) || !form.name.trim() || !form.subject.trim() || variables.length > 20 || new Set(variables).size !== variables.length || variables.some(value => !/^[a-z][a-z0-9_]{0,31}$/.test(value))) { formError.value = uiText('请填写有效编码、名称、标题和不重复的变量'); return }
  saving.value = true; formError.value = ''
  try {
    await messagesApi.save(form.id, { code: form.code, name: form.name.trim(), enabled: form.enabled, revision: form.revision, subject: form.subject, body: form.body, variables })
    if (!guard.isCurrent()) return
    guard.markClean(); editorOpen.value = false; ElMessage.success(uiText('保存成功')); await load()
  } catch (exception: unknown) { if (guard.isCurrent()) { if (responseStatus(exception) === 409 && form.id) conflict.mark(); else formError.value = uiText('保存失败，已保留输入；请检查占位符与声明变量') } }
  finally { saving.value = false }
}
async function compose(row: MessageTemplate) {
  if (!canSend.value || saving.value || !row.enabled) return
  if (!row.current) { ElMessage.error(uiText('模板当前版本缺失，请由管理员修复后重试')); return }; clearDraft(); selected.value = row; values.value = Object.fromEntries((row.current?.variables || []).map(key => [key, ''])); sendOpen.value = true
  const current = ++channelGeneration; channelController = new AbortController(); channelLoading.value = true
  try {
    const data = await messagesApi.channels(channelController.signal)
    if (current === channelGeneration && sendOpen.value && guard.isCurrent()) { available.value = { inapp: data.some(item => item.key === 'inapp' && item.enabled), email: data.some(item => item.key === 'email' && item.enabled), webhook: data.some(item => item.key === 'webhook' && item.enabled), sms: data.some(item => item.key === 'sms' && item.enabled) }; channels.value = available.value.inapp ? ['inapp'] : [] }
  } catch { if (current === channelGeneration && guard.isCurrent()) formError.value = uiText('投递渠道加载失败，请关闭后重试') }
  finally { if (current === channelGeneration) channelLoading.value = false }
}
function addRecipient() { if (!saving.value && picked.value && !recipients.value.some(person => person.id === picked.value?.id) && recipients.value.length < 100) { recipients.value.push(picked.value); picked.value = null } }
function removeRecipient(id: string) { if (!saving.value) recipients.value = recipients.value.filter(person => person.id !== id) }
async function makePreview() {
  if (saving.value || !selected.value || !sendOpen.value || !guard.isCurrent()) return
  invalidatePreview(); const current = previewGeneration; previewController = new AbortController(); previewing.value = true; formError.value = ''
  try { const data = await messagesApi.preview(selected.value.id, selected.value.revision, { ...values.value }, previewController.signal); if (current === previewGeneration && sendOpen.value && guard.isCurrent()) preview.value = data }
  catch { if (current === previewGeneration && guard.isCurrent()) formError.value = uiText('预览失败，请检查变量或重新打开最新模板') }
  finally { if (current === previewGeneration) previewing.value = false }
}
async function send() {
  if (saving.value || previewing.value || !sendOpen.value || !selected.value || !preview.value || !guard.isCurrent() || !canSend.value || !recipients.value.length || !channels.value.length || channels.value.some(key => !available.value[key])) return
  const id = selected.value.id, data = { revision: selected.value.revision, values: { ...values.value }, recipient_ids: recipients.value.map(person => person.id), channels: [...channels.value] }, body = JSON.stringify(data)
  if (!sendKey || sendBody !== body) { sendKey = newIdempotencyKey('template-send'); sendBody = body }
  saving.value = true; formError.value = ''
  try {
    ownsConfirmation = true
    await ElMessageBox.confirm(uiText('确定向所选人员登记通知投递吗？'), uiText('提示'), { confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), closeOnClickModal: false })
    ownsConfirmation = false
    if (!guard.isCurrent() || !canSend.value) return
    await messagesApi.send(id, data, sendKey)
    if (!guard.isCurrent()) return
    guard.markClean(); sendOpen.value = false; tab.value = 'deliveries'; ElMessage.success(uiText('已登记投递，请查看结果')); resetList()
  } catch (exception) { if (exception !== 'cancel' && exception !== 'close' && guard.isCurrent()) formError.value = uiText('发送未确认，已保留输入；检查模板、人员和邮箱后重试') }
  finally { ownsConfirmation = false; saving.value = false }
}
async function retry(row: MessageDelivery) {
  if (!canSend.value || saving.value) return
  saving.value = true
  try { await messagesApi.retry(row.id); if (canSend.value && guard.isSessionCurrent()) { ElMessage.success(uiText('已登记重试')); await load() } }
  catch { if (canSend.value && guard.isSessionCurrent()) error.value = uiText('重试未确认，请刷新检查状态、期限与次数') }
  finally { saving.value = false }
}
function history(row: MessageTemplate) { if (!canRead.value) return; historyId.value = row.id; historyPage.value = 1; historyOpen.value = true; void loadHistory() }
function clearHistory() { historyGeneration++; historyController?.abort(); versions.value = []; historyId.value = ''; historyLoading.value = false; historyError.value = false; historyTotal.value = 0 }
async function loadHistory() {
  if (!historyOpen.value || !canRead.value || !historyId.value) return
  const current = ++historyGeneration; historyController?.abort(); historyController = new AbortController(); versions.value = []; historyLoading.value = true; historyError.value = false
  try { const data = await messagesApi.versions(historyId.value, historyPage.value, historyController.signal); if (current === historyGeneration && historyOpen.value && canRead.value && guard.isSessionCurrent()) { versions.value = data.items; historyTotal.value = data.pagination.total } }
  catch { if (current === historyGeneration && canRead.value && guard.isSessionCurrent()) historyError.value = true }
  finally { if (current === historyGeneration) historyLoading.value = false }
}
watch(historyOpen, open => { if (!open) clearHistory() }, { flush: 'sync' })
function clearSensitive() { generation++; listController?.abort(); templates.value = []; deliveries.value = []; loading.value = false; total.value = 0; clearDraft(); historyOpen.value = false; clearHistory() }
watch(() => JSON.stringify([sessionIdentity(auth.token), auth.user?.id, auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, auth.user?.must_change_password, modules.enabled('notifications')]), () => { clearSensitive(); if (canRead.value) void load() }, { flush: 'sync' })
onMounted(load)
onActivated(() => { if (!active.value) { active.value = true; void load() } })
onDeactivated(() => { active.value = false; clearSensitive() })
onBeforeUnmount(() => { active.value = false; clearSensitive() })
</script>

<style scoped>
h2 { margin: 0; font-size: var(--font-size-lg); }
.heading, .recipients { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); align-items: center; }
.heading { justify-content: space-between; }
.notice { color: var(--color-text-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.status-filter { width: 150px; }
.preview { margin-top: var(--spacing-md); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--spacing-md); }
.preview h3, .preview p { white-space: pre-wrap; overflow-wrap: anywhere; }
.recipients { margin-bottom: var(--spacing-md); }
.recipients :deep(.el-tag) { max-width: 100%; height: auto; min-height: 24px; white-space: normal; overflow-wrap: anywhere; }
:deep(.action-buttons .el-button) { min-height: 44px; min-width: 44px; }
@media (max-width: 640px) { .filters :deep(.el-form-item) { display: flex; margin-right: 0; } }
</style>
