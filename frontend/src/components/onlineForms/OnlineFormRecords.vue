<template>
  <section class="records" :aria-label="uiText('我的表单记录')">
    <div class="records-head">
      <h3>{{ uiText('我的表单记录') }}</h3>
      <el-button :loading="loading" :disabled="saving || !canRead" @click="load">{{ uiText('刷新记录') }}</el-button>
    </div>
    <p class="hint">{{ uiText('历史记录按提交时的表单版本显示，修改仍使用原字段规则') }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="items" stripe :empty-text="uiText('暂无记录')">
      <el-table-column prop="form_name" :label="uiText('名称')" min-width="120" />
      <el-table-column prop="release_number" :label="uiText('发布版本')" width="100" />
      <el-table-column :label="uiText('审批状态')" width="110"><template #default="{ row }">{{ approvalLabel(row.approval_status) }}</template></el-table-column>
      <el-table-column prop="created_at" :label="uiText('提交时间')" min-width="190" />
      <el-table-column :label="uiText('操作')" width="100">
        <template #default="{ row }"><el-button :disabled="saving || loading || detailLoading" @click="open(row.id)">{{ uiText('查看记录') }}</el-button></template>
      </el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next, total" :disabled="loading || saving" @current-change="load" />
    <el-dialog v-model="visible" :title="uiText('表单记录')" width="min(900px, 94vw)" :before-close="close" :close-on-click-modal="false">
      <p v-if="detailLoading" role="status">{{ uiText('记录加载中') }}</p>
      <template v-if="record">
        <p>{{ record.form_name }} · {{ uiText('发布版本') }} {{ record.release_number }}</p>
        <p v-if="record.approval_enabled || record.approval_request">{{ uiText('审批状态') }}：{{ approvalLabel(record.approval_status) }} <router-link v-if="record.approval_request" to="/approvals">{{ uiText('查看审批') }}</router-link></p>
        <OnlineFormRenderer v-model="values" :definition="record.definition_snapshot" :errors="errors" :disabled="!editing || saving" :attachment-context="{ code, recordId: record.id }" />
        <p v-if="detailError" ref="errorSummary" role="alert" tabindex="-1" class="failure">{{ detailError }}</p>
        <p v-if="feedback" role="status">{{ feedback }}</p>
      </template>
      <p v-else-if="detailError" role="alert" class="failure">{{ detailError }}</p>
      <template #footer>
        <el-button :disabled="saving" @click="close()">{{ uiText('关闭') }}</el-button>
        <el-button v-if="record && !editing && canUpdate && mutable" :disabled="saving" @click="editing = true">{{ uiText('修改记录') }}</el-button>
        <el-button v-if="record && editing && canUpdate" type="primary" :loading="saving" @click="save">{{ uiText('保存记录') }}</el-button>
        <el-button v-if="record?.approval_enabled && !editing && mutable && canSubmit" :loading="saving" @click="approvalAction('submit')">{{ uiText('提交审批') }}</el-button>
        <el-button v-if="record?.approval_status === 'pending' && !editing && canWithdraw" :loading="saving" @click="approvalAction('withdraw')">{{ uiText('撤回审批') }}</el-button>
      </template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import './lifecycleMessages'
import { computed, nextTick, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useLatestRead } from '@/composables/useLatestRead'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { onlineFormLifecycleApi, type OnlineFormHistoryDetail, type OnlineFormHistoryRow } from '@/api/onlineFormLifecycle'
import { errorMessage } from '@/api/request'
import { uiText } from '@/i18n/uiText'
import OnlineFormRenderer from './OnlineFormRenderer.vue'
import { submissionValues, fieldErrors, type FormValues } from './runtime'
const props = defineProps<{ code: string; refresh?: number }>()
const auth = useAuthStore()
const tenants = useTenantStore()
const canRead = computed(() => auth.can('online_form:record_read'))
const canUpdate = computed(() => auth.can('online_form:record_update'))
const canSubmit = computed(() => auth.can('online_form:record_submit'))
const canWithdraw = computed(() => auth.can('online_form:record_withdraw'))
const mutable = computed(() => !['pending', 'approved'].includes(record.value?.approval_status || 'draft'))
function approvalLabel(status?: string) {
  return uiText(({ draft: '未送审', pending: '审批中', approved: '已通过', rejected: '已驳回', cancelled: '已撤回' } as Record<string, string>)[status || 'draft'] || '未送审')
}
const items = ref<OnlineFormHistoryRow[]>([]), total = ref(0), page = ref(1), loading = ref(false), error = ref('')
const visible = ref(false), detailLoading = ref(false), record = ref<OnlineFormHistoryDetail>(), values = ref<FormValues>({})
const editing = ref(false), saving = ref(false), detailError = ref(''), feedback = ref(''), errors = ref<Record<string, string>>({})
const errorSummary = ref<HTMLElement>()
const beginRead = useLatestRead(() => { items.value = []; total.value = 0; error.value = ''; loading.value = false })
const beginDetail = useLatestRead(clearDetail)
function clearDetail() { record.value = undefined; values.value = {}; visible.value = false; editing.value = false; detailError.value = ''; errors.value = {}; feedback.value = ''; detailLoading.value = false }
const guard = useUnsavedChanges({ source: () => values.value, active: () => visible.value, busy: () => saving.value, clear: clearDetail })
async function load() {
  const current = beginRead()
  if (!canRead.value) return
  loading.value = true; error.value = ''
  try {
    const result = await onlineFormLifecycleApi.records(props.code, page.value)
    if (current()) { items.value = result.items; total.value = result.pagination.total }
  } catch (err) { if (current()) error.value = errorMessage(err, uiText('记录加载失败，请重试')) }
  finally { if (current()) loading.value = false }
}
async function open(id: string) {
  if (!canRead.value || saving.value || detailLoading.value) return
  if (!(await guard.confirmDiscard())) return
  clearDetail(); visible.value = true; detailLoading.value = true
  const current = beginDetail()
  try {
    const result = await onlineFormLifecycleApi.detail(props.code, id)
    if (current()) { record.value = result; values.value = JSON.parse(JSON.stringify(result.data)); guard.markClean() }
  } catch (err) { if (current()) detailError.value = errorMessage(err, uiText('记录加载失败，请重试')) }
  finally { if (current()) detailLoading.value = false }
}
async function close(done?: () => void) {
  if (saving.value || !(await guard.confirmDiscard())) return
  beginDetail(); clearDetail(); done?.()
}
async function save() {
  if (!record.value || !editing.value || saving.value || !canRead.value || !canUpdate.value) return
  const current = beginDetail(), code = props.code, row = record.value
  saving.value = true; detailError.value = ''; errors.value = {}; feedback.value = ''
  try {
    const data = row.definition_snapshot.schema_version === 2 ? submissionValues(row.definition_snapshot.fields, values.value) : values.value
    const result = await onlineFormLifecycleApi.update(code, row.id, data, row.version)
    if (current() && guard.isSessionCurrent()) {
      record.value = result; values.value = JSON.parse(JSON.stringify(result.data)); editing.value = false; guard.markClean()
      feedback.value = uiText('记录已保存'); await load()
    }
  } catch (err) {
    if (current() && guard.isSessionCurrent()) {
      errors.value = fieldErrors(err); detailError.value = errorMessage(err, uiText('保存失败，请检查字段或重新打开记录'))
      await nextTick(); errorSummary.value?.focus()
    }
  } finally { saving.value = false }
}
async function approvalAction(operation: 'submit' | 'withdraw') {
  if (!record.value || editing.value || saving.value || !canRead.value || !(operation === 'submit' ? canSubmit.value : canWithdraw.value)) return
  const current = beginDetail(), code = props.code, row = record.value
  saving.value = true; detailError.value = ''; feedback.value = ''
  try {
    const result = await (operation === 'submit' ? onlineFormLifecycleApi.submitApproval : onlineFormLifecycleApi.withdrawApproval)(code, row.id, row.version)
    if (current() && guard.isSessionCurrent()) {
      record.value = result; values.value = JSON.parse(JSON.stringify(result.data)); guard.markClean()
      feedback.value = uiText(operation === 'submit' ? '审批已提交' : '审批已撤回'); await load()
    }
  } catch (err) {
    if (current() && guard.isSessionCurrent()) { detailError.value = errorMessage(err, uiText('审批操作失败，请刷新记录后重试')); await nextTick(); errorSummary.value?.focus() }
  } finally { saving.value = false }
}
watch([() => props.code, canRead, () => tenants.currentId], () => { beginDetail(); clearDetail(); items.value = []; total.value = 0; page.value = 1; void load() }, { immediate: true, flush: 'sync' })
watch(() => props.refresh, () => { void load() })
watch(canUpdate, value => { if (!value) { editing.value = false; if (record.value) values.value = JSON.parse(JSON.stringify(record.value.data)) } })
</script>
<style scoped>
.records { min-width: 0; margin-top: 24px; }
.records-head { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.hint { color: var(--el-text-color-secondary); line-height: 1.6; }
.failure { color: var(--el-color-danger); overflow-wrap: anywhere; }
.records :deep(.el-pagination) { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
@media (max-width: 768px) { .records-head { align-items: flex-start; flex-direction: column; } .records :deep(button) { min-height: 44px; } }
</style>
