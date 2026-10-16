<template>
  <AppLayout>
    <div class="flow-page">
      <BaseCard>
        <template #header>
          <div class="header-row">
            <div><div class="title">{{ uiText('审批流程设计器') }}</div><div class="subtitle">{{ uiText('以节点和连线配置流程，发布后版本不可直接修改') }}</div></div>
            <div class="actions">
              <BaseButton @click="newFlow">{{ uiText('新建草稿') }}</BaseButton>
              <BaseButton variant="primary" :disabled="!editing || saving" @click="saveFlow">{{ uiText('保存草稿') }}</BaseButton>
              <BaseButton v-if="editing?.status === 'draft'" variant="primary" :disabled="saving" @click="publishFlow">{{ uiText('发布') }}</BaseButton>
            </div>
          </div>
        </template>
        <el-alert v-if="error" :title="error" type="error" :closable="false" class="mb" />
        <el-empty v-if="!loading && flows.length === 0" :description="uiText('暂无流程草稿，请新建')" />
        <el-table v-else :data="flows" stripe @row-click="selectFlow">
          <el-table-column prop="name" :label="uiText('名称')" min-width="180" />
          <el-table-column prop="code" :label="uiText('编码')" min-width="160" />
          <el-table-column prop="version" :label="uiText('版本')" width="90" />
          <el-table-column :label="uiText('状态')" width="110"><template #default="{ row }"><el-tag>{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column :label="uiText('操作')" width="150"><template #default="{ row }"><el-button link type="primary" @click.stop="selectFlow(row)">{{ uiText('编辑') }}</el-button></template></el-table-column>
        </el-table>
      </BaseCard>

      <BaseCard v-if="editing" class="editor-card">
        <template #header><div class="title">{{ editing.status === 'draft' ? uiText('编辑流程') : uiText('流程详情') }}</div></template>
        <el-form label-width="90px" :disabled="editing.status !== 'draft' || saving">
          <el-form-item :label="uiText('流程名称')"><el-input v-model="editing.name" /></el-form-item>
          <el-form-item :label="uiText('流程编码')"><el-input v-model="editing.code" /></el-form-item>
        </el-form>
        <div class="section-head"><span>{{ uiText('节点') }}</span><el-button size="small" :disabled="editing.status !== 'draft'" @click="addNode">{{ uiText('添加节点') }}</el-button></div>
        <el-table :data="nodes" border>
          <el-table-column :label="uiText('标识')" min-width="140"><template #default="{ row }"><el-input v-model="row.id" :disabled="editing.status !== 'draft'" /></template></el-table-column>
          <el-table-column :label="uiText('类型')" width="140"><template #default="{ row }"><el-select v-model="row.type" :disabled="editing.status !== 'draft'"><el-option label="start" value="start" /><el-option label="user" value="user" /><el-option label="parallel" value="parallel" /><el-option label="or" value="or" /><el-option label="end" value="end" /></el-select></template></el-table-column>
          <el-table-column :label="uiText('审批人 ID（逗号分隔）')" min-width="260"><template #default="{ row }"><el-input v-model="row.assigneeText" :disabled="editing.status !== 'draft' || !isApproval(row)" /></template></el-table-column>
          <el-table-column :label="uiText('模式')" width="120"><template #default="{ row }"><el-select v-model="row.mode" :disabled="editing.status !== 'draft' || !isApproval(row)"><el-option label="all" value="all" /><el-option label="any" value="any" /></el-select></template></el-table-column>
          <el-table-column :label="uiText('操作')" width="80"><template #default="{ $index }"><el-button link type="danger" :disabled="editing.status !== 'draft'" @click="removeNode($index)">×</el-button></template></el-table-column>
        </el-table>
        <div class="section-head edge-head"><span>{{ uiText('连线（起点 → 终点）') }}</span><el-button size="small" :disabled="editing.status !== 'draft'" @click="addEdge">{{ uiText('添加连线') }}</el-button></div>
        <el-table :data="edges" border>
          <el-table-column :label="uiText('起点')"><template #default="{ row }"><el-input v-model="row.from" :disabled="editing.status !== 'draft'" /></template></el-table-column>
          <el-table-column label="→" width="60" align="center" />
          <el-table-column :label="uiText('终点')"><template #default="{ row }"><el-input v-model="row.to" :disabled="editing.status !== 'draft'" /></template></el-table-column>
          <el-table-column :label="uiText('操作')" width="80"><template #default="{ $index }"><el-button link type="danger" :disabled="editing.status !== 'draft'" @click="edges.splice($index, 1)">×</el-button></template></el-table-column>
        </el-table>
      </BaseCard>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseCard } from '@/components'
import { approvalFlowsApi, type ApprovalFlowRow } from '@/api'
import { uiText } from '@/i18n/uiText'

type EditableNode = { id: string; type: string; mode: 'all' | 'any'; assigneeText: string }
type EditableEdge = { from: string; to: string }
const flows = ref<ApprovalFlowRow[]>([])
const editing = ref<ApprovalFlowRow | null>(null)
const nodes = ref<EditableNode[]>([])
const edges = ref<EditableEdge[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const statusLabel = (status: string) => ({ draft: uiText('草稿'), published: uiText('已发布'), archived: uiText('已归档') }[status] || status)
const isApproval = (node: EditableNode) => ['user', 'parallel', 'or'].includes(node.type)

function loadEditor(flow: ApprovalFlowRow) {
  editing.value = JSON.parse(JSON.stringify(flow))
  nodes.value = (flow.definition.nodes || []).map((row) => ({ id: String(row.id || ''), type: String(row.type || 'user'), mode: row.mode === 'any' ? 'any' : 'all', assigneeText: Array.isArray(row.assignee_ids) ? row.assignee_ids.join(',') : '' }))
  edges.value = (flow.definition.edges || []).map((row) => ({ from: String(row.from || ''), to: String(row.to || '') }))
}
async function load() { loading.value = true; error.value = ''; try { flows.value = (await approvalFlowsApi.list({ page: 1, page_size: 100 })).items } catch (err) { error.value = err instanceof Error ? err.message : uiText('流程列表加载失败') } finally { loading.value = false } }
function selectFlow(flow: ApprovalFlowRow) { loadEditor(flow) }
function newFlow() { loadEditor({ id: '', name: '', code: '', status: 'draft', version: 1, definition: { nodes: [{ id: 'start', type: 'start' }, { id: 'approve', type: 'user', mode: 'all', assignee_ids: [] }, { id: 'end', type: 'end' }], edges: [{ from: 'start', to: 'approve' }, { from: 'approve', to: 'end' }] } }) }
function addNode() { nodes.value.splice(Math.max(nodes.value.length - 1, 0), 0, { id: 'node-' + nodes.value.length, type: 'user', mode: 'all', assigneeText: '' }) }
function removeNode(index: number) { nodes.value.splice(index, 1) }
function addEdge() { edges.value.push({ from: '', to: '' }) }
function definition() { return { nodes: nodes.value.map((node) => ({ id: node.id.trim(), type: node.type, ...(isApproval(node) ? { mode: node.mode, assignee_ids: node.assigneeText.split(',').map((id) => id.trim()).filter(Boolean) } : {}) })), edges: edges.value.map((edge) => ({ from: edge.from.trim(), to: edge.to.trim() })) } }
async function saveFlow() { if (!editing.value) return; saving.value = true; try { const payload = { name: editing.value.name, code: editing.value.code, definition: definition() }; const response = editing.value.id ? await approvalFlowsApi.update(editing.value.id, payload) : await approvalFlowsApi.create(payload); loadEditor(response.data.data || response.data); await load(); ElMessage.success(uiText('流程草稿已保存')) } catch (err) { ElMessage.error(err instanceof Error ? err.message : uiText('保存失败')) } finally { saving.value = false } }
async function publishFlow() { if (!editing.value?.id) { await saveFlow(); if (!editing.value?.id) return }; saving.value = true; try { const response = await approvalFlowsApi.publish(editing.value.id); loadEditor(response.data.data || response.data); await load(); ElMessage.success(uiText('流程已发布')) } catch (err) { ElMessage.error(err instanceof Error ? err.message : uiText('发布失败')) } finally { saving.value = false } }
onMounted(load)
</script>

<style scoped>
.flow-page { display: grid; gap: 16px; }
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
