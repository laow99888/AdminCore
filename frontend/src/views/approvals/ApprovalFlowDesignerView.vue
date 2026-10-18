<template>
  <AppLayout>
    <div class="flow-page">
      <BaseCard>
        <template #header>
          <div class="header-row">
            <div><div class="title">{{ uiText('审批流程设计器') }}</div><div class="subtitle">{{ uiText('以节点和连线配置流程，发布后版本不可直接修改') }}</div></div>
            <div class="actions">
              <BaseButton :disabled="saving" @click="newFlow">{{ uiText('新建草稿') }}</BaseButton>
              <BaseButton variant="primary" :disabled="!editing || editing.status !== 'draft' || saving" @click="saveFlow">{{ uiText('保存草稿') }}</BaseButton>
              <BaseButton v-if="editing?.status === 'draft'" variant="primary" :disabled="saving" @click="publishFlow">{{ uiText('发布') }}</BaseButton>
              <BaseButton v-if="editing?.id && editing.status !== 'draft'" :disabled="saving" @click="createRevision">{{ uiText('新建版本') }}</BaseButton>
              <BaseButton v-if="editing?.id && editing.status !== 'archived'" :disabled="saving" @click="archiveFlow">{{ uiText('归档流程') }}</BaseButton>
            </div>
          </div>
        </template>
        <el-alert v-if="error" :title="error" type="error" :closable="false" class="mb" />
        <el-empty v-if="!loading && flows.length === 0" :description="uiText('暂无流程草稿，请新建')" />
        <el-table v-else :data="flows" stripe @row-click="selectFlow">
          <el-table-column prop="name" :label="uiText('名称')" min-width="180" />
          <el-table-column prop="code" :label="uiText('编码')" min-width="160" />
          <el-table-column :label="uiText('发布版次')" width="100"><template #default="{ row }">v{{ row.revision || 1 }}</template></el-table-column>
          <el-table-column prop="version" :label="uiText('编辑版本')" width="100" />
          <el-table-column :label="uiText('状态')" width="110"><template #default="{ row }"><el-tag>{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column :label="uiText('操作')" width="150"><template #default="{ row }"><el-button link type="primary" @click.stop="selectFlow(row)">{{ uiText('编辑') }}</el-button></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next, total" :disabled="saving" @current-change="load" />
      </BaseCard>

      <BaseCard v-if="editing" class="editor-card">
        <template #header><div class="title">{{ editing.status === 'draft' ? uiText('编辑流程') : uiText('流程详情') }}</div></template>
        <el-form label-width="90px" :disabled="editing.status !== 'draft' || saving">
          <el-form-item :label="uiText('流程名称')"><el-input v-model="editing.name" /></el-form-item>
          <el-form-item :label="uiText('流程编码')"><el-input v-model="editing.code" :disabled="!!editing.id" /></el-form-item>
          <el-form-item :label="uiText('条件流程 V2')"><el-switch v-model="versionTwo" :aria-label="uiText('条件流程 V2')" /></el-form-item>
          <template v-if="versionTwo">
            <el-alert :title="uiText('条件按连线顺序匹配，未匹配时走默认出口；每条路径必须经过审批')" type="info" :closable="false" />
            <el-button class="mb" :disabled="inputs.length >= 20" @click="inputs.push({ key: '', type: 'decimal' })">{{ uiText('添加流程输入') }}</el-button>
            <div v-for="(input, index) in inputs" :key="index" class="input-row">
              <el-input v-model="input.key" :aria-label="uiText('流程输入字段') + ' ' + (index + 1)" maxlength="30" />
              <el-select v-model="input.type" :aria-label="uiText('流程输入类型') + ' ' + (index + 1)"><el-option v-for="kind in ['text', 'integer', 'decimal', 'boolean', 'date']" :key="kind" :label="kind" :value="kind" /></el-select>
              <el-button :aria-label="uiText('删除流程输入') + ' ' + (index + 1)" @click="inputs.splice(index, 1)">{{ uiText('删除') }}</el-button>
            </div>
          </template>
        </el-form>
        <div class="section-head"><span>{{ uiText('节点') }}</span><el-button size="small" :disabled="editing.status !== 'draft' || saving" @click="addNode">{{ uiText('添加节点') }}</el-button></div>
        <el-table :data="nodes" border>
          <el-table-column :label="uiText('标识')" min-width="140"><template #default="{ row }"><el-input v-model="row.id" :disabled="editing.status !== 'draft' || saving" /></template></el-table-column>
          <el-table-column :label="uiText('类型')" width="140"><template #default="{ row }"><el-select v-model="row.type" :disabled="editing.status !== 'draft' || saving"><el-option label="start" value="start" /><el-option label="user" value="user" /><el-option label="parallel" value="parallel" /><el-option label="or" value="or" /><el-option label="end" value="end" /><el-option v-if="versionTwo" :label="uiText('条件分支')" value="branch" /></el-select></template></el-table-column>
          <el-table-column v-if="versionTwo" :label="uiText('审批人来源')" min-width="180"><template #default="{ row }"><el-select v-model="row.source" :aria-label="uiText('审批人来源')" :disabled="editing.status !== 'draft' || saving || !isApproval(row)"><el-option :label="uiText('固定人员')" value="fixed" /><el-option :label="uiText('申请人')" value="applicant" /><el-option :label="uiText('角色成员')" value="role" /><el-option :label="uiText('部门主管')" value="department_leader" /></el-select></template></el-table-column>
          <el-table-column v-if="versionTwo" :label="uiText('主管层级')" min-width="180"><template #default="{ row }"><el-input-number v-if="row.source === 'department_leader' && isApproval(row)" v-model="row.levels" :min="1" :max="10" :precision="0" :aria-label="uiText('主管层级')" :disabled="editing.status !== 'draft' || saving" /></template></el-table-column>
          <el-table-column :label="uiText('审批人 ID（逗号分隔）')" min-width="260"><template #default="{ row }"><el-input v-model="row.assigneeText" :aria-label="uiText(row.source === 'role' ? '审批角色 ID' : '审批人 ID（逗号分隔）')" :disabled="editing.status !== 'draft' || saving || !isApproval(row) || (versionTwo && ['applicant', 'department_leader'].includes(row.source))" /></template></el-table-column>
          <el-table-column :label="uiText('模式')" width="120"><template #default="{ row }"><el-select v-model="row.mode" :disabled="editing.status !== 'draft' || saving || !isApproval(row)"><el-option label="all" value="all" /><el-option label="any" value="any" /></el-select></template></el-table-column>
          <el-table-column v-if="versionTwo" :label="uiText('超时运营')" min-width="280"><template #default="{ row }">
            <div v-if="isApproval(row)" class="timeout-config">
              <label>{{ uiText('提醒时限（分钟）') }}<el-input-number v-model="row.timeoutMinutes" :min="0" :max="525600" :precision="0" :aria-label="uiText('提醒时限分钟，0关闭')" :disabled="editing.status !== 'draft' || saving" /></label>
              <template v-if="row.timeoutMinutes > 0">
                <label>{{ uiText('升级时限（分钟）') }}<el-input-number v-model="row.escalateMinutes" :min="0" :max="525600" :precision="0" :aria-label="uiText('升级时限分钟，0关闭')" :disabled="editing.status !== 'draft' || saving" /></label>
                <label v-if="row.escalateMinutes > 0">{{ uiText('升级接收人') }}<PersonPicker v-model="row.escalatePerson" purpose="approval" :disabled="editing.status !== 'draft' || saving" /></label>
                <WorkingCalendarEditor v-model="row.calendar" :disabled="editing.status !== 'draft' || saving" />
              </template>
            </div>
          </template></el-table-column>
          <el-table-column :label="uiText('操作')" width="80"><template #default="{ $index }"><el-button link type="danger" :disabled="editing.status !== 'draft' || saving" :aria-label="uiText('删除节点')" @click="removeNode($index)">×</el-button></template></el-table-column>
        </el-table>
        <p v-if="versionTwo">{{ uiText('主管层级1为主职部门，2为上级部门，最多10级；任期或主管无效时阻止推进，不自动跳过。') }}</p>
        <p v-if="versionTwo">{{ uiText('时限从进入节点起计算，0为关闭；升级晚于提醒，只发送站内通知，不自动改派或通过。新版本发布只影响新申请。') }}</p>
        <div class="section-head edge-head"><span>{{ uiText('连线（起点 → 终点）') }}</span><el-button size="small" :disabled="editing.status !== 'draft' || saving" @click="addEdge">{{ uiText('添加连线') }}</el-button></div>
        <el-table :data="edges" border>
          <el-table-column :label="uiText('起点')"><template #default="{ row }"><el-input v-model="row.from" :disabled="editing.status !== 'draft' || saving" /></template></el-table-column>
          <el-table-column label="→" width="60" align="center" />
          <el-table-column :label="uiText('终点')"><template #default="{ row }"><el-input v-model="row.to" :disabled="editing.status !== 'draft' || saving" /></template></el-table-column>
          <el-table-column v-if="versionTwo" :label="uiText('出口条件')" min-width="340"><template #default="{ row }">
            <div v-if="nodes.some(node => node.id === row.from && node.type === 'branch')" class="edge-condition">
              <el-switch v-model="row.fallback" :active-text="uiText('默认出口')" :disabled="editing.status !== 'draft' || saving" />
              <template v-if="!row.fallback"><el-select v-model="row.field" :aria-label="uiText('条件字段')" :disabled="editing.status !== 'draft' || saving"><el-option v-for="input in inputs" :key="input.key" :label="input.key" :value="input.key" /></el-select>
              <el-select v-model="row.op" :aria-label="uiText('比较操作')" :disabled="editing.status !== 'draft' || saving"><el-option v-for="op in ['eq', 'ne', 'lt', 'lte', 'gt', 'gte']" :key="op" :label="op" :value="op" /></el-select>
              <el-input v-model="row.value" :aria-label="uiText('比较值')" :disabled="editing.status !== 'draft' || saving" /></template>
            </div>
          </template></el-table-column>
          <el-table-column :label="uiText('操作')" width="180"><template #default="{ $index }"><el-button link type="danger" :disabled="editing.status !== 'draft' || saving" :aria-label="uiText('删除连线')" @click="edges.splice($index, 1)">{{ uiText('删除') }}</el-button><el-button link :aria-label="uiText('上移连线')" :disabled="editing.status !== 'draft' || saving || $index === 0" @click="moveEdge($index, -1)">{{ uiText('上移') }}</el-button><el-button link :aria-label="uiText('下移连线')" :disabled="editing.status !== 'draft' || saving || $index === edges.length - 1" @click="moveEdge($index, 1)">{{ uiText('下移') }}</el-button></template></el-table-column>
        </el-table>
      </BaseCard>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useLatestRead } from '@/composables/useLatestRead'
import { errorMessage, notifyError } from '@/api/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import PersonPicker from '@/components/common/PersonPicker.vue'
import type { Person } from '@/api/personnel'
import WorkingCalendarEditor from './WorkingCalendarEditor.vue'
import { validateWorkingCalendar, type WorkingCalendar } from './workingCalendar'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseCard } from '@/components'
import { approvalFlowsApi, type ApprovalFlowRow } from '@/api'
import { uiText } from '@/i18n/uiText'
import '@/components/codegen/messages'
import './messages'

type EditableNode = { id: string; type: string; mode: 'all' | 'any'; assigneeText: string; source: 'fixed' | 'applicant' | 'role' | 'department_leader'; levels: number; timeoutMinutes: number; escalateMinutes: number; escalatePerson: Person | null; calendar: WorkingCalendar | null }
type EditableEdge = { from: string; to: string; fallback: boolean; field: string; op: string; value: string }
const versionTwo = ref(false)
const inputs = ref<Array<{ key: string; type: string }>>([])
const flows = ref<ApprovalFlowRow[]>([])
const editing = ref<ApprovalFlowRow | null>(null)
const nodes = ref<EditableNode[]>([])
const edges = ref<EditableEdge[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const statusLabel = (status: string) => ({ draft: uiText('草稿'), published: uiText('已发布'), archived: uiText('已归档') }[status] || status)
const isApproval = (node: EditableNode) => ['user', 'parallel', 'or'].includes(node.type)

const page = ref(1), total = ref(0)
const beginRead = useLatestRead(() => { flows.value = []; total.value = 0 })
const guard = useUnsavedChanges({ source: () => editing.value?.status === 'draft' ? { editing: editing.value, nodes: nodes.value, edges: edges.value, versionTwo: versionTwo.value, inputs: inputs.value } : null, busy: () => saving.value, clear: () => { editing.value = null; nodes.value = []; edges.value = []; inputs.value = []; versionTwo.value = false } })
function loadEditor(flow: ApprovalFlowRow) {
  editing.value = JSON.parse(JSON.stringify(flow))
  versionTwo.value = flow.definition.schema_version === 2
  inputs.value = JSON.parse(JSON.stringify(flow.definition.inputs || []))
  nodes.value = (flow.definition.nodes || []).map((row) => {
    const source = row.assignee as { source: 'applicant' | 'role' | 'department_leader'; role_id?: string; levels?: number } | undefined
    const timeout = row.timeout as { minutes: number; escalate_after_minutes?: number; escalate_to?: string; calendar?: WorkingCalendar } | undefined
    return { id: String(row.id || ''), type: String(row.type || 'user'), mode: row.mode === 'any' ? 'any' : 'all', source: source?.source || 'fixed', levels: source?.levels || 1, assigneeText: source?.role_id || (Array.isArray(row.assignee_ids) ? row.assignee_ids.join(',') : ''), timeoutMinutes: timeout?.minutes || 0, escalateMinutes: timeout?.escalate_after_minutes || 0, escalatePerson: timeout?.escalate_to ? { id: timeout.escalate_to, display_name: timeout.escalate_to, username: timeout.escalate_to } as Person : null, calendar: timeout?.calendar ? JSON.parse(JSON.stringify(timeout.calendar)) : null }
  })
  edges.value = (flow.definition.edges || []).map((row) => {
    const condition = row.when as { field: string; op: string; value: unknown } | undefined
    return { from: String(row.from || ''), to: String(row.to || ''), fallback: row.default === true, field: condition?.field || '', op: condition?.op || 'gte', value: condition ? String(condition.value) : '' }
  })
  guard.markClean()
}
async function load() { const current = beginRead(); try { const data = await approvalFlowsApi.list({ page: page.value, page_size: 20 }); if (current()) { flows.value = data.items; total.value = data.pagination.total } } catch (err) { if (current()) error.value = errorMessage(err, uiText('列表加载失败')) } }
async function selectFlow(row: ApprovalFlowRow) { if (!saving.value && await guard.confirmDiscard()) loadEditor(row) }
async function newFlow() { if (saving.value || !await guard.confirmDiscard()) return; loadEditor({ id: '', name: '', code: '', status: 'draft', version: 1, definition: { nodes: [{ id: 'start', type: 'start' }, { id: 'approve', type: 'user', mode: 'all', assignee_ids: [] }, { id: 'end', type: 'end' }], edges: [{ from: 'start', to: 'approve' }, { from: 'approve', to: 'end' }] } }) }
function addNode() { nodes.value.splice(Math.max(nodes.value.length - 1, 0), 0, { id: 'node-' + crypto.randomUUID(), type: 'user', mode: 'all', assigneeText: '', source: 'fixed', levels: 1, timeoutMinutes: 0, escalateMinutes: 0, escalatePerson: null, calendar: null }) }
function removeNode(index: number) { nodes.value.splice(index, 1) }
function addEdge() { edges.value.push({ from: '', to: '', fallback: false, field: '', op: 'gte', value: '' }) }
function moveEdge(index: number, offset: number) {
  const [edge] = edges.value.splice(index, 1)
  if (edge) edges.value.splice(index + offset, 0, edge)
}
function definition(): ApprovalFlowRow['definition'] {
  for (const node of nodes.value) {
    if (versionTwo.value && isApproval(node) && node.timeoutMinutes > 0 && node.calendar) validateWorkingCalendar(node.calendar)
    if (versionTwo.value && isApproval(node) && node.timeoutMinutes > 0 && node.escalateMinutes > 0 &&
        (node.escalateMinutes <= node.timeoutMinutes || !node.escalatePerson)) throw new Error(uiText('升级时限须晚于提醒并选择接收人'))
  }
  const value = (edge: EditableEdge) => {
    const kind = inputs.value.find(input => input.key === edge.field)?.type
    if (kind === 'integer') { if (!/^-?[0-9]+$/.test(edge.value)) throw new Error(uiText('整数条件值无效')); return Number(edge.value) }
    if (kind === 'boolean') { if (!['true', 'false'].includes(edge.value)) throw new Error(uiText('布尔条件请填写 true 或 false')); return edge.value === 'true' }
    return edge.value
  }
  return {
    ...(versionTwo.value ? { schema_version: 2 as const, inputs: inputs.value } : {}),
    nodes: nodes.value.map(node => ({ id: node.id.trim(), type: node.type, ...(isApproval(node) ? { mode: node.mode,
      ...(versionTwo.value && node.timeoutMinutes > 0 ? { timeout: { minutes: node.timeoutMinutes, ...(node.calendar ? { calendar: node.calendar } : {}), ...(node.escalateMinutes > 0 ? { escalate_after_minutes: node.escalateMinutes, escalate_to: node.escalatePerson!.id } : {}) } } : {}),
      ...(versionTwo.value && node.source !== 'fixed' ? { assignee: { source: node.source, ...(node.source === 'role' ? { role_id: node.assigneeText.trim() } : node.source === 'department_leader' ? { levels: node.levels } : {}) } } : { assignee_ids: node.assigneeText.split(',').map(id => id.trim()).filter(Boolean) }) } : {}) })),
    edges: edges.value.map(edge => ({ from: edge.from.trim(), to: edge.to.trim(),
      ...(versionTwo.value && nodes.value.some(node => node.id === edge.from && node.type === 'branch') ? edge.fallback ? { default: true } : { when: { field: edge.field, op: edge.op, value: value(edge) } } : {}) })),
  }
}
async function saveFlow(): Promise<boolean> {
  if (!editing.value || editing.value.status !== 'draft' || saving.value) return false
  saving.value = true
  try {
    const payload = { name: editing.value.name, code: editing.value.code, definition: definition(), version: editing.value.version }
    const response = editing.value.id ? await approvalFlowsApi.update(editing.value.id, payload) : await approvalFlowsApi.create(payload)
    if (!guard.isSessionCurrent()) return false
    loadEditor(response.data.data || response.data); await load(); ElMessage.success(uiText('流程草稿已保存')); return true
  } catch (err) { notifyError(err, uiText('保存失败')); return false } finally { saving.value = false }
}
async function publishFlow() {
  if (saving.value || editing.value?.status !== 'draft') return
  if ((!editing.value.id || guard.dirty.value) && !await saveFlow()) return
  if (!editing.value?.id) return
  saving.value = true
  try { const response = await approvalFlowsApi.publish(editing.value.id, editing.value.version); if (!guard.isSessionCurrent()) return; loadEditor(response.data.data || response.data); await load(); ElMessage.success(uiText('已发布')) }
  catch (err) { notifyError(err, uiText('发布失败')) } finally { saving.value = false }
}
async function createRevision() {
  if (saving.value || !editing.value?.id || !await guard.confirmDiscard()) return
  saving.value = true
  try { const response = await approvalFlowsApi.newRevision(editing.value.id); if (!guard.isSessionCurrent()) return; loadEditor(response.data.data); await load(); ElMessage.success(uiText('已创建新版本草稿')) }
  catch (err) { notifyError(err, uiText('操作失败')) } finally { saving.value = false }
}
async function archiveFlow() {
  if (saving.value || !editing.value?.id || !await guard.confirmDiscard()) return
  try { await ElMessageBox.confirm(uiText('归档后停止接收新申请，在途申请继续使用原版本。'), uiText('归档流程'), { type: 'warning' }) } catch { return }
  saving.value = true
  try { const response = await approvalFlowsApi.archive(editing.value.id); if (!guard.isSessionCurrent()) return; loadEditor(response.data.data); await load(); ElMessage.success(uiText('已归档')) }
  catch (err) { notifyError(err, uiText('操作失败')) } finally { saving.value = false }
}
onMounted(load)
</script>

<style scoped>
.flow-page { display: grid; gap: 16px; min-width: 0; }
.input-row { display: flex; gap: 8px; margin-bottom: 8px; }
.input-row > * { min-width: 0; }
.edge-condition { display: grid; gap: 8px; }
.timeout-config { display: grid; gap: 8px; }
.timeout-config label { display: grid; gap: 4px; }
.header-row, .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.title { font-weight: 600; font-size: 16px; }
.subtitle { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.editor-card { overflow: hidden; }
.section-head { margin: 20px 0 10px; font-weight: 600; }
.edge-head { margin-top: 24px; }
.mb { margin-bottom: 12px; }
@media (max-width: 768px) { .header-row { align-items: flex-start; flex-direction: column; } .actions { width: 100%; } .actions :deep(button) { flex: 1; } }
</style>
