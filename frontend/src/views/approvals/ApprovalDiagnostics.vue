<template>
  <section v-if="admin" class="approval-diagnostics" :aria-label="uiText('审批阻塞诊断')">
    <div class="diagnostic-header"><strong>{{ requestId ? uiText('审批阻塞诊断') : uiText('主动巡检') }}</strong>
      <el-button :loading="loading" :disabled="loading" @click="load(false)">{{ requestId ? uiText('重新诊断') : uiText('扫描待批申请') }}</el-button>
      <el-button v-if="!requestId && cursor" :disabled="loading" @click="load(true)">{{ uiText('扫描下一批') }}</el-button>
    </div>
    <p>{{ uiText('诊断为当前状态快照，不修改审批；未来人员仅检查实际条件路径，后续组织变化需重新诊断。') }}</p>
    <el-alert v-if="error" :title="uiText('诊断失败，请重试')" type="error" :closable="false" />
    <p v-if="checkedAt">{{ uiText('检查时间') }}: {{ checkedAt }} · {{ uiText('已扫描') }} {{ scanned }}</p>
    <el-empty v-if="checkedAt && !items.length && !error" :description="uiText('本批未发现已检查范围内的问题')" />
    <div v-for="item in items" :key="item.request_id" class="diagnostic-item">
      <code v-if="!requestId">{{ item.request_id }}</code>
      <el-tag :type="item.blocked ? 'danger' : 'warning'">{{ item.blocked ? uiText('存在阻塞') : uiText('需要关注') }}</el-tag>
      <span>{{ item.scope === 'current' ? uiText('当前节点') : uiText('当前及未来实际路径') }}</span>
      <ul><li v-for="(issue, index) in item.issues" :key="index">{{ issue.node ? issue.node + ': ' : '' }}{{ issueName(issue.code) }}</li></ul>
      <el-button v-if="!requestId" :disabled="loading" @click="inspect(item.request_id)">{{ uiText('检查未来路径') }}</el-button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { approvalDiagnosticsApi, type ApprovalDiagnostic } from '@/api/approvalDiagnostics'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useLatestRead } from '@/composables/useLatestRead'
import { uiText } from '@/i18n/uiText'
import './messages'
const props = defineProps<{ requestId?: string; workflowVersion?: number }>()
const tenant = useTenantStore()
const auth = useAuthStore(), admin = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser))
const loading = ref(false), error = ref(false), items = ref<ApprovalDiagnostic[]>([]), cursor = ref<string | null>(null), checkedAt = ref(''), scanned = ref(0)
function clear() { items.value = []; cursor.value = null; checkedAt.value = ''; scanned.value = 0; loading.value = false; error.value = false }
const beginRead = useLatestRead(clear)
watch(() => [props.requestId, props.workflowVersion, admin.value, tenant.currentId], () => { beginRead(); clear() }, { flush: 'sync' })
async function load(next = false) {
  if (!admin.value || loading.value) return
  const current = beginRead(), selected = next ? cursor.value : null
  loading.value = true; error.value = false
  try {
    if (props.requestId) { const data = await approvalDiagnosticsApi.request(props.requestId); if (current()) { items.value = data.issues.length ? [data] : []; checkedAt.value = data.checked_at; scanned.value = 1 } }
    else { const data = await approvalDiagnosticsApi.health(selected || undefined); if (current()) { items.value = data.items; cursor.value = data.next_cursor; checkedAt.value = data.checked_at; scanned.value = data.scanned } }
  } catch { if (current()) error.value = true } finally { if (current()) loading.value = false }
}
async function inspect(id: string) {
  if (!admin.value || loading.value) return
  const current = beginRead(); loading.value = true; error.value = false
  try { const data = await approvalDiagnosticsApi.request(id); if (current()) items.value = items.value.map(item => item.request_id === id ? data : item) }
  catch { if (current()) error.value = true } finally { if (current()) loading.value = false }
}
const labels: Record<string, string> = {
  applicant_unavailable: '申请人账号或租户成员身份已失效', assignee_unavailable: '审批人账号或租户成员身份已失效，可在异常待办修复', assignee_password_required: '审批人必须先完成密码修改，再处理审批', delegate_unavailable: '委托人已失效或必须先修改密码',
  pending_step_missing: '当前节点缺少待办，请核对流程状态', pending_step_mismatch: '待办节点或访问序次不一致，请核对流程状态',
  no_available_reviewer: '当前节点没有可操作的审批人', reminder_recipient_unavailable: '提醒接收人已失效', escalation_recipient_unavailable: '升级接收人已失效',
  timeout_delivery_failed: '超时通知等待修复重试', overdue: '当前待办已超过提醒时限', business_module_unavailable: '关联业务模块已关闭',
  future_assignment_unavailable: '后续节点审批人无法解析，请修复人员或组织配置', flow_state_invalid: '冻结流程或输入状态无效，请核对流程版本',
}
const issueName = (code: string) => uiText(labels[code] || '未知诊断问题，请刷新或联系管理员')
</script>
<style scoped>
.approval-diagnostics { min-width: 0; margin: 12px 0; overflow-wrap: anywhere; }
.diagnostic-header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.diagnostic-item { border-top: 1px solid var(--el-border-color-lighter); padding: 8px 0; }
.diagnostic-item > span, .diagnostic-item > code { margin-right: 8px; }
p { color: var(--el-text-color-secondary); }
</style>
