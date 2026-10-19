<template>
  <AppLayout>
    <div class="approval-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("审批工作流") }}</div>
            <BaseButton variant="primary" @click="handleCreate">{{ uiText("+ 发起申请") }}</BaseButton>
          </div>
        </template>

        <!-- 视角切换 -->
        <el-tabs v-model="activeBox" class="box-tabs" @tab-change="handleBoxChange">
          <el-tab-pane :label="uiText('待我审批')" name="todo" />
          <el-tab-pane :label="uiText('我已处理')" name="done" />
          <el-tab-pane :label="uiText('我的申请')" name="sent" />
          <el-tab-pane :label="uiText('抄送我的')" name="cc" />
          <el-tab-pane v-if="auth.user?.is_staff || auth.user?.is_superuser" :label="uiText('异常审批')" name="exceptions" />
        </el-tabs>
        <ApprovalDiagnostics v-if="activeBox === 'exceptions'" />

        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :action-width="220"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <el-button link type="primary" size="small" @click="showDetail(row)">{{ uiText("详情") }}</el-button>
            <template v-if="activeBox === 'todo'">
              <el-button link type="success" size="small" @click="handleApprove(row)">{{ uiText("通过") }}</el-button>
              <el-button link type="danger" size="small" @click="handleReject(row)">{{ uiText("驳回") }}</el-button>
            </template>
            <template v-else-if="activeBox === 'sent' && row.status === 'pending'">
              <el-button link type="warning" size="small" @click="handleCancel(row)">{{ uiText("撤回") }}</el-button>
            </template>
            <span v-else class="no-action">—</span>
          </template>
        </BaseTable>
      </BaseCard>

      <BaseDialog v-model="detailVisible" :title="uiText('申请详情')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="detailVisible = false">
        <el-descriptions v-if="currentApproval" :column="1" border>
          <el-descriptions-item :label="uiText('标题')">{{ currentApproval.title }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('申请人')">{{ currentApproval.applicant_name }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('审批人')">{{ currentApproval.assignee_name }}</el-descriptions-item>
          <el-descriptions-item :label="uiText('内容')"><div style="white-space: pre-wrap; overflow-wrap: anywhere">{{ currentApproval.content }}</div></el-descriptions-item>
          <el-descriptions-item :label="uiText('审批意见')"><div style="white-space: pre-wrap; overflow-wrap: anywhere">{{ currentApproval.decision_comment || '—' }}</div></el-descriptions-item>
          <el-descriptions-item :label="uiText('处理时间')">{{ currentApproval.decided_at || '—' }}</el-descriptions-item>
        </el-descriptions>
        <pre v-if="currentApproval?.business_module" class="business-snapshot" :aria-label="uiText('提交时的业务快照')">{{ JSON.stringify(currentApproval.business_snapshot, null, 2) }}</pre>
        <el-table v-if="currentApproval?.steps?.length" :data="currentApproval.steps">
          <el-table-column prop="node_key" :label="uiText('节点')" />
          <el-table-column prop="assignee_name" :label="uiText('审批人')" />
          <el-table-column :label="uiText('主管解析记录')" min-width="200"><template #default="{ row }"><span v-if="row.assignment_context?.source === 'department_leader'">{{ row.assignment_context.department_name }} · {{ row.assignment_context.assignee_name }} · {{ row.assignment_context.resolved_on }}</span><span v-else>—</span></template></el-table-column>
          <el-table-column prop="delegated_to_name" :label="uiText('受托人')" />
          <el-table-column prop="status" :label="uiText('状态')" />
        </el-table>
        <ApprovalOperations v-if="detailVisible && currentApproval" :application="currentApproval" @changed="updateDetail" />
        <div v-if="currentApproval?.status === 'pending'" class="advanced-actions">
          <el-button v-if="ownStep" :disabled="saving" @click="openAction('addSign')">{{ uiText('加签') }}</el-button>
          <el-button v-if="ownStep?.assignee === auth.user?.id" :disabled="saving" @click="openAction('transfer')">{{ uiText('转交') }}</el-button>
          <el-button v-if="ownStep?.assignee === auth.user?.id" :disabled="saving" @click="openAction('delegate')">{{ uiText('委托') }}</el-button>
          <el-button v-if="activeBox !== 'cc'" :disabled="saving" @click="openAction('cc')">{{ uiText('抄送') }}</el-button>
          <el-button v-if="activeBox === 'exceptions'" :disabled="saving" @click="openAction('repairStep')">{{ uiText('修复审批人') }}</el-button>
        </div>
      </BaseDialog>
      <!-- 发起申请 -->
      <BaseDialog v-model="createVisible" :before-close="formGuard.confirmDiscard" :title="uiText('发起审批申请')" :loading="saving" @confirm="handleSubmit">
        <el-alert v-if="submitError" :title="uiText('提交失败，输入已保留；请重新选择审批人后重试')" type="error" :closable="false" />
        <el-form :model="createForm" label-width="90px" :disabled="saving">
          <el-form-item :label="uiText('标题')" required>
            <el-input v-model="createForm.title" :placeholder="uiText('申请标题')" />
          </el-form-item>
          <el-form-item :label="uiText('类型')">
            <el-select v-model="createForm.request_type" style="width: 100%">
              <el-option :label="uiText('请假')" value="leave" />
              <el-option :label="uiText('采购')" value="purchase" />
              <el-option :label="uiText('权限申请')" value="permission" />
              <el-option :label="uiText('其他')" value="other" />
            </el-select>
          </el-form-item>
          <el-form-item :label="uiText('审批流程')">
            <el-select v-model="flowId" clearable filterable :loading="flowsLoading" @visible-change="loadFlows" style="width: 100%">
              <el-option v-for="flow in availableFlows" :key="flow.id" :label="`${flow.name} (v${flow.revision || 1})`" :value="flow.id" />
            </el-select>
            <el-button v-if="flowsHasMore" link :disabled="flowsLoading" @click="loadFlows(true, true)">{{ uiText('加载更多流程') }}</el-button>
          </el-form-item>
          <el-form-item v-if="!flowId" :label="uiText('审批人')" required>
            <PersonPicker v-model="assignee" purpose="approval" :disabled="saving || !createVisible" />
          </el-form-item>
          <el-form-item v-for="field in selectedFlowInputs" :key="field.key" :label="field.key" required>
            <el-switch v-if="field.type === 'boolean'" v-model="flowValues[field.key]" :aria-label="field.key" />
            <el-input-number v-else-if="field.type === 'integer'" v-model="flowValues[field.key]" :aria-label="field.key" :precision="0" :min="-2147483648" :max="2147483647" />
            <el-input v-else v-model="flowValues[field.key]" :aria-label="field.key" :placeholder="field.type === 'date' ? 'YYYY-MM-DD' : field.type === 'decimal' ? '0.00' : ''" />
          </el-form-item>
          <el-form-item :label="uiText('内容')" required>
            <el-input v-model="createForm.content" type="textarea" :rows="4" :placeholder="uiText('申请说明')" />
          </el-form-item>
        </el-form>
      </BaseDialog>
      <BaseDialog v-model="actionVisible" :before-close="actionGuard.confirmDiscard" :title="actionLabels[actionKind]" :loading="saving" @confirm="submitAction">
        <el-form label-width="90px" :disabled="saving">
          <el-form-item v-if="actionKind === 'repairStep' && currentApproval?.flow" :label="uiText('待处理步骤')" required>
            <el-select v-model="repairStepId"><el-option v-for="step in currentApproval?.steps?.filter(item => item.status === 'pending')" :key="step.id" :label="`${step.node_key} / ${step.assignee_name || '—'}`" :value="step.id" /></el-select>
          </el-form-item>
          <el-form-item :label="uiText('目标人员')" required><PersonPicker v-model="actionTarget" purpose="approval" :disabled="saving || !actionVisible" /></el-form-item>
          <el-form-item :label="uiText('审批意见')"><el-input v-model="actionComment" type="textarea" :maxlength="4000" /></el-form-item>
        </el-form>
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import '@/components/codegen/messages'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useActionGuard } from '@/composables/useActionGuard'
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { computed, reactive, ref, watch } from 'vue'
import PersonPicker from '@/components/common/PersonPicker.vue'
import ApprovalOperations from './ApprovalOperations.vue'
import ApprovalDiagnostics from './ApprovalDiagnostics.vue'
import { approvalDiagnosticsApi } from '@/api/approvalDiagnostics'
import type { Person } from '@/api/personnel'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { approvalsApi, approvalFlowsApi, newIdempotencyKey, type ApprovalRow, type ApprovalBox, type ApprovalFlowRow } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { notifyError } from '@/api/request'
import { useRealtimeUpdates } from '@/composables/useRealtimeUpdates'
import { useLatestRead } from '@/composables/useLatestRead'

const loading = ref(false)
const saving = ref(false)
const auth = useAuthStore()
const flowId = ref(''), availableFlows = ref<ApprovalFlowRow[]>([]), flowsLoading = ref(false), flowsHasMore = ref(false)
// 与 API 的受限输入契约一致；金额始终使用文本，不转换为浮点数。
const flowValues = reactive<Record<string, any>>({})
const selectedFlowInputs = computed(() => availableFlows.value.find(flow => flow.id === flowId.value)?.definition.inputs || [])
watch(flowId, () => {
  for (const key of Object.keys(flowValues)) delete flowValues[key]
  for (const field of selectedFlowInputs.value) flowValues[field.key] = field.type === 'boolean' ? false : field.type === 'integer' ? 0 : ''
})
let flowsPage = 0
const beginFlowRead = useLatestRead(() => { availableFlows.value = []; flowsPage = 0; flowsHasMore.value = false; flowsLoading.value = false })
async function loadFlows(visible = true, more = false) {
  if (!visible || flowsLoading.value || (!more && flowsPage)) return
  const current = beginFlowRead()
  flowsLoading.value = true
  try { const data = await approvalFlowsApi.list({ status: 'published', page: more ? flowsPage + 1 : 1, page_size: 20 }); if (!current()) return; availableFlows.value = more ? [...availableFlows.value, ...data.items] : data.items; flowsPage = data.pagination.page; flowsHasMore.value = flowsPage < data.pagination.total_pages }
  catch (error) { if (current()) notifyError(error, uiText('操作失败')) }
  finally { if (current()) flowsLoading.value = false }
}
const actionVisible = ref(false), actionTarget = ref<Person | null>(null), actionComment = ref('')
const actionKind = ref<'addSign' | 'transfer' | 'delegate' | 'cc' | 'repairStep'>('cc')
const repairStepId = ref('')
const actionLabels = { addSign: uiText('加签'), transfer: uiText('转交'), delegate: uiText('委托'), cc: uiText('抄送'), repairStep: uiText('修复审批人') }
const ownStep = computed(() => currentApproval.value?.steps?.find(step => step.status === 'pending' &&
  (step.assignee === auth.user?.id || step.delegated_to === auth.user?.id)))
const actionGuard = useUnsavedChanges({ source: () => [actionTarget.value, actionComment.value], active: () => actionVisible.value,
  busy: () => saving.value, clear: () => { actionVisible.value = false; actionTarget.value = null; actionComment.value = '' } })
function showDetail(row: ApprovalRow) { currentApproval.value = row; detailVisible.value = true }
function updateDetail(row: ApprovalRow) { currentApproval.value = row; void loadList() }
function openAction(kind: typeof actionKind.value) { actionKind.value = kind; actionTarget.value = null; actionComment.value = ''; repairStepId.value = currentApproval.value?.steps?.find(step => step.status === 'pending')?.id || ''; actionVisible.value = true }
async function submitAction() {
  if (saving.value || !currentApproval.value || !actionTarget.value) return
  saving.value = true
  try {
    const id = currentApproval.value.id, target = actionTarget.value.id, kind = actionKind.value
    const repair = currentApproval.value.steps?.find(step => step.id === repairStepId.value)
    if (kind === 'repairStep' && currentApproval.value.flow && !repair) return
    const response = kind === 'cc' ? await approvalsApi.cc(id, [target], actionComment.value) : kind === 'repairStep'
      ? currentApproval.value.flow ? await approvalsApi.repairStep(id, target, repair!.id, repair!.version, actionComment.value)
        : await approvalDiagnosticsApi.repairLegacy(id, target, currentApproval.value.workflow_version!, actionComment.value)
      : await approvalsApi[kind](id, target, actionComment.value, ownStep.value?.version, currentApproval.value.workflow_version)
    if (!actionGuard.isSessionCurrent()) return
    currentApproval.value = response.data.data; actionVisible.value = false; ElMessage.success(uiText('操作成功')); await loadList()
  } catch (error) { notifyError(error, uiText('操作失败')) } finally { saving.value = false }
}
const dialogOpen = ref(false)
const createVisible = computed({ get: () => dialogOpen.value, set: value => { if (!saving.value) dialogOpen.value = value } })
const assignee = ref<Person | null>(null)
const submitError = ref(false)
const detailVisible = ref(false)
const currentApproval = ref<ApprovalRow | null>(null)
const activeBox = ref<ApprovalBox>('todo')
const tableData = ref<ApprovalRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

usePageState({ activeBox, currentPage, pageSize })
const STATUS_LABELS: Record<string, string> = {
  pending: uiText("待审批"),
  approved: uiText("已通过"),
  rejected: uiText("已驳回"),
  cancelled: uiText("已撤回"),
}
const TYPE_LABELS: Record<string, string> = {
  leave: uiText("请假"),
  purchase: uiText("采购"),
  permission: uiText("权限申请"),
  other: uiText("其他"),
}

const createForm = reactive({
  title: '',
  request_type: 'other',
  content: '',
})

const formGuard = useUnsavedChanges({ source: () => ({ form: createForm, assignee: assignee.value, flow: flowId.value, flowValues }), active: () => createVisible.value, busy: () => saving.value, clear: () => { dialogOpen.value = false; assignee.value = null; flowId.value = ''; Object.assign(createForm, { title: '', request_type: 'other', content: '' }) } })
const tableColumns = [
  { prop: 'title', label: uiText("标题") },
  { prop: 'request_type', label: uiText("类型"), width: '100px', render: (v: string) => TYPE_LABELS[v] || v },
  { prop: 'applicant_name', label: uiText("申请人"), width: '110px' },
  { prop: 'assignee_name', label: uiText("审批人"), width: '110px' },
  {
    prop: 'status',
    label: uiText("状态"),
    width: '100px',
    render: (v: string) => STATUS_LABELS[v] || v,
  },
  { prop: 'created_at', label: uiText("提交时间"), width: '180px' },
]

const loadList = async () => {
  const current = beginRead()
  loading.value = true
  try {
    const data = await approvalsApi.list(activeBox.value, {
      page: currentPage.value,
      page_size: pageSize.value,
    })
    if (current()) { tableData.value = data.items; total.value = data.pagination.total }
  } catch (error) {
    if (current()) notifyError(error, uiText('列表加载失败'))
  } finally {
    if (current()) loading.value = false
  }
}

const handleBoxChange = () => {
  currentPage.value = 1
  loadList()
}

const handleCreate = () => {
  submission = undefined
  assignee.value = null
  flowId.value = ''
  submitError.value = false
  Object.assign(createForm, { title: '', request_type: 'other', content: '' })
  createVisible.value = true
}

let submission: { fingerprint: string; key: string } | undefined

const handleSubmit = async () => {
  if (saving.value) return
  if (!createForm.title.trim() || !createForm.content.trim() || (!flowId.value && !assignee.value)) {
    ElMessage.warning(uiText("请填写标题、审批人和申请内容"))
    return
  }
  saving.value = true
  submitError.value = false
  const payload = {
    title: createForm.title,
    request_type: createForm.request_type,
    content: createForm.content,
    ...(flowId.value ? { flow_id: flowId.value, ...(availableFlows.value.find(flow => flow.id === flowId.value)?.definition.schema_version === 2 ? { extra_data: { ...flowValues } } : {}) } : { assignee_id: assignee.value!.id }),
  }
  const fingerprint = JSON.stringify(payload)
  if (submission?.fingerprint !== fingerprint) {
    submission = { fingerprint, key: newIdempotencyKey('approval-create') }
  }
  try {
    await approvalsApi.create(payload, submission.key)
    submission = undefined
    ElMessage.success(uiText("申请已提交"))
    dialogOpen.value = false
    activeBox.value = 'sent'
    loadList()
  } catch {
    submitError.value = true
  } finally {
    saving.value = false
  }
}

const decide = async (row: ApprovalRow, action: 'approve' | 'reject') => {
  const tip = action === 'approve' ? uiText("通过") : uiText("驳回")
  try {
    const { value } = await ElMessageBox.prompt(uiText("审批意见（可留空）"), uiText("{p0}申请「{p1}」", { p0: tip, p1: row.title }), {
      confirmButtonText: tip,
      cancelButtonText: uiText("取消"),
      inputPlaceholder: uiText("审批意见"),
    })
    const step = row.steps?.find(item => item.status === 'pending' && (item.assignee === auth.user?.id || item.delegated_to === auth.user?.id))
    await approvalsApi[action](row.id, value, row.workflow_version, step?.id)
    ElMessage.success(uiText("已{p0}", { p0: tip }))
    loadList()
  } catch {
    // 用户取消
  }
}

const handleApprove = (row: ApprovalRow) => decide(row, 'approve')
const handleReject = (row: ApprovalRow) => decide(row, 'reject')

const beginAction = useActionGuard()
const handleCancel = (row: ApprovalRow) => {
  const isCurrent = beginAction()
  ElMessageBox.confirm(uiText("确定撤回申请「{p0}」吗？", { p0: row.title }), uiText("提示"), { type: 'warning' })
    .then(async () => {
      if (!isCurrent()) return
      await approvalsApi.cancel(row.id)
      if (!isCurrent()) return
      ElMessage.success(uiText("已撤回"))
      loadList()
    })
    .catch(() => {})
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadList()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadList()
}

const beginRead = useRealtimeUpdates('approvals', loadList, () => { tableData.value = []; total.value = 0; loading.value = false; currentApproval.value = null; detailVisible.value = false })
loadList()
</script>

<style scoped>
.business-snapshot { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 400px; overflow: auto; }
.approval-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.box-tabs {
  margin-bottom: var(--spacing-md);
}

.no-action {
  color: var(--color-text-tertiary);
}
.advanced-actions { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); margin-top: var(--spacing-md); }
</style>
