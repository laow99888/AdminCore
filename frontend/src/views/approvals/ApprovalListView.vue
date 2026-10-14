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
        </el-tabs>

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
            <el-button link type="primary" size="small" @click="currentApproval = row; detailVisible = true">{{ uiText("详情") }}</el-button>
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
          <el-form-item :label="uiText('审批人')" required>
            <PersonPicker v-model="assignee" purpose="approval" :disabled="saving || !createVisible" />
          </el-form-item>
          <el-form-item :label="uiText('内容')" required>
            <el-input v-model="createForm.content" type="textarea" :rows="4" :placeholder="uiText('申请说明')" />
          </el-form-item>
        </el-form>
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { computed, reactive, ref } from 'vue'
import PersonPicker from '@/components/common/PersonPicker.vue'
import type { Person } from '@/api/personnel'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { approvalsApi, newIdempotencyKey, type ApprovalRow, type ApprovalBox } from '@/api'
import { useRealtimeUpdates } from '@/composables/useRealtimeUpdates'

const loading = ref(false)
const saving = ref(false)
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

const formGuard = useUnsavedChanges({ source: () => ({ form: createForm, assignee: assignee.value }), active: () => createVisible.value, busy: () => saving.value, clear: () => { dialogOpen.value = false; assignee.value = null; Object.assign(createForm, { title: '', request_type: 'other', content: '' }) } })
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
  submitError.value = false
  Object.assign(createForm, { title: '', request_type: 'other', content: '' })
  createVisible.value = true
}

let submission: { fingerprint: string; key: string } | undefined

const handleSubmit = async () => {
  if (saving.value) return
  if (!createForm.title.trim() || !createForm.content.trim() || !assignee.value) {
    ElMessage.warning(uiText("请填写标题、审批人和申请内容"))
    return
  }
  saving.value = true
  submitError.value = false
  const payload = {
    title: createForm.title,
    request_type: createForm.request_type,
    content: createForm.content,
    assignee_id: assignee.value.id,
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
    await (action === 'approve' ? approvalsApi.approve(row.id, value) : approvalsApi.reject(row.id, value))
    ElMessage.success(uiText("已{p0}", { p0: tip }))
    loadList()
  } catch {
    // 用户取消
  }
}

const handleApprove = (row: ApprovalRow) => decide(row, 'approve')
const handleReject = (row: ApprovalRow) => decide(row, 'reject')

const handleCancel = (row: ApprovalRow) => {
  ElMessageBox.confirm(uiText("确定撤回申请「{p0}」吗？", { p0: row.title }), uiText("提示"), { type: 'warning' })
    .then(async () => {
      await approvalsApi.cancel(row.id)
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
</style>
