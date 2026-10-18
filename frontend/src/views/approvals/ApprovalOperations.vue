<template>
  <section class="approval-operations" :aria-label="uiText('流程运营')">
    <p v-if="application.flow">{{ uiText('发布版次') }} v{{ application.flow_revision || 1 }} · {{ uiText('退回次数') }} {{ application.return_count || 0 }}</p>
    <ApprovalDiagnostics v-if="admin" :request-id="application.id" :workflow-version="application.workflow_version" />
    <div v-for="step in timedSteps" :key="step.id" class="timeout-row">
      <span>{{ step.node_key }} · {{ step.assignee_name || '—' }}</span>
      <span>{{ uiText('提醒截止') }}: {{ step.due_at }}</span>
      <el-tag v-if="step.timeout_error" type="danger">{{ uiText('超时通知接收人异常') }}</el-tag>
      <span v-else-if="step.reminded_at">{{ uiText('提醒已进入通知队列') }}</span>
      <span v-if="step.escalated_at && !step.timeout_error?.includes('escalate')">{{ uiText('升级通知已进入队列') }}</span>
      <el-button v-if="admin && step.timeout_error" :disabled="saving" @click="open('retry', step)">{{ uiText('修复并重试提醒') }}</el-button>
    </div>
    <el-button v-if="canReturn" :disabled="saving" @click="open('return')">{{ uiText('退回指定节点') }}</el-button>
    <div class="history-header"><strong>{{ uiText('审批操作记录') }}</strong><el-button :loading="loading" @click="loadHistory">{{ uiText('刷新') }}</el-button></div>
    <el-alert v-if="historyError" :title="uiText('操作记录加载失败，请重试')" type="error" :closable="false" />
    <el-table v-loading="loading" :data="history" :empty-text="uiText('暂无操作记录')">
      <el-table-column :label="uiText('操作')" min-width="130"><template #default="{ row }">{{ actionName(row.action) }}</template></el-table-column>
      <el-table-column :label="uiText('操作人')" min-width="110"><template #default="{ row }">{{ row.actor_name || uiText('系统任务') }}</template></el-table-column>
      <el-table-column :label="uiText('结果或意见')" min-width="220"><template #default="{ row }"><span>{{ row.comment || (row.metadata.outcome === 'unavailable' ? uiText('接收人无效，等待管理员处理') : row.metadata.outcome === 'queued' ? uiText('已入队，送达状态请查看通知中心') : row.metadata.target_node || '—') }}</span></template></el-table-column>
      <el-table-column prop="created_at" :label="uiText('时间')" min-width="200" />
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next, total" :disabled="loading" @current-change="loadHistory" />
    <BaseDialog v-model="visible" :title="kind === 'return' ? uiText('退回指定节点') : uiText('修复并重试提醒')" :loading="saving" :before-close="guard.confirmDiscard" @confirm="submit">
      <el-alert :title="kind === 'return' ? uiText('退回后重新进入所选节点，原记录保留，后续环节重新审批，业务仍锁定。') : uiText('只重试接收人异常的通知；可选更换升级接收人，不改变审批人或数据权限。')" type="info" :closable="false" />
      <el-form label-position="top" :disabled="saving">
        <el-form-item v-if="kind === 'return'" :label="uiText('退回节点')" required><el-select v-model="targetNode" :aria-label="uiText('退回节点')"><el-option v-for="node in application.returnable_nodes" :key="node" :label="node" :value="node" /></el-select></el-form-item>
        <el-form-item v-else-if="selectedStep?.timeout_error?.includes('escalate')" :label="uiText('升级接收人（可选）')"><PersonPicker v-model="targetPerson" purpose="approval" :disabled="saving || !visible" /></el-form-item>
        <el-form-item :label="uiText('操作原因')" required><el-input v-model="comment" type="textarea" :maxlength="4000" :aria-label="uiText('操作原因')" /></el-form-item>
      </el-form>
    </BaseDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { BaseDialog } from '@/components'
import PersonPicker from '@/components/common/PersonPicker.vue'
import type { Person } from '@/api/personnel'
import { approvalsApi, newIdempotencyKey, type ApprovalRow, type ApprovalStepRow, type ApprovalHistoryRow } from '@/api'
import { notifyError } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { useLatestRead } from '@/composables/useLatestRead'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { uiText } from '@/i18n/uiText'
import './messages'
import ApprovalDiagnostics from './ApprovalDiagnostics.vue'

const props = defineProps<{ application: ApprovalRow }>()
const emit = defineEmits<{ changed: [application: ApprovalRow] }>()
const auth = useAuthStore()
const admin = computed(() => auth.user?.is_staff || auth.user?.is_superuser)
const own = computed(() => props.application.steps?.some(step => step.status === 'pending' && [step.assignee, step.delegated_to].includes(auth.user?.id)))
const canReturn = computed(() => props.application.status === 'pending' && own.value && !!props.application.returnable_nodes?.length)
const timedSteps = computed(() => props.application.steps?.filter(step => step.status === 'pending' && step.due_at) || [])
const page = ref(1), total = ref(0), history = ref<ApprovalHistoryRow[]>([]), loading = ref(false), historyError = ref(false)
const beginRead = useLatestRead(() => { history.value = []; total.value = 0; loading.value = false })
async function loadHistory() {
  const current = beginRead(); loading.value = true; historyError.value = false
  try { const data = await approvalsApi.history(props.application.id, { page: page.value, page_size: 20 }); if (current()) { history.value = data.items; total.value = data.pagination.total } }
  catch (error) { if (current()) { historyError.value = true; notifyError(error, uiText('操作记录加载失败，请重试')) } }
  finally { if (current()) loading.value = false }
}
watch(() => props.application.id, () => { page.value = 1; void loadHistory() }, { immediate: true })
const labels: Record<string, string> = { approve: '通过', reject: '驳回', return: '退回指定节点', add_sign: '加签', transfer: '转交', delegate: '委托', cc: '抄送', cancel: '撤回', remind: '超时提醒', escalate: '超时升级', retry_timeout: '重试超时通知' }
const actionName = (key: string) => uiText(labels[key] || key)
const kind = ref<'return' | 'retry'>('return'), visible = ref(false), saving = ref(false)
const comment = ref(''), targetNode = ref(''), selectedStep = ref<ApprovalStepRow | null>(null), targetPerson = ref<Person | null>(null)
const guard = useUnsavedChanges({ source: () => [comment.value, targetNode.value, targetPerson.value], active: () => visible.value, busy: () => saving.value,
  clear: () => { visible.value = false; comment.value = ''; targetPerson.value = null } })
let submission: { fingerprint: string; key: string } | undefined
function open(operation: typeof kind.value, step?: ApprovalStepRow) {
  kind.value = operation; selectedStep.value = step || null; targetNode.value = props.application.returnable_nodes?.[0] || ''; comment.value = ''; targetPerson.value = null; submission = undefined; visible.value = true
}
async function submit() {
  if (saving.value || !comment.value.trim() || (kind.value === 'return' && !targetNode.value)) { if (!saving.value) ElMessage.warning(uiText('请选择节点并填写操作原因')); return }
  saving.value = true
  const applicationId = props.application.id
  try {
    const fingerprint = JSON.stringify([props.application.id, props.application.workflow_version, targetNode.value, comment.value])
    if (submission?.fingerprint !== fingerprint) submission = { fingerprint, key: newIdempotencyKey('approval-return') }
    const response = kind.value === 'return'
      ? await approvalsApi.returnNode(props.application.id, targetNode.value, props.application.workflow_version!, comment.value, submission.key)
      : await approvalsApi.retryTimeout(props.application.id, selectedStep.value!.id, selectedStep.value!.version, comment.value, targetPerson.value?.id)
    if (!guard.isSessionCurrent() || props.application.id !== applicationId) return
    visible.value = false; emit('changed', response.data.data); ElMessage.success(uiText('操作成功')); await loadHistory()
  } catch (error) { if (guard.isSessionCurrent()) notifyError(error, uiText('操作失败，输入已保留')) } finally { saving.value = false }
}
</script>

<style scoped>
.approval-operations { min-width: 0; margin-top: 16px; }
.timeout-row, .history-header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0; overflow-wrap: anywhere; }
.history-header { justify-content: space-between; }
</style>
