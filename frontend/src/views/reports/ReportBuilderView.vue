<template>
  <AppLayout>
    <div class="report-workbench">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div class="report-workbench-layout">
        <el-card shadow="never" class="report-design-card">
          <template #header><div class="builder-header"><span>{{ uiText('报表构建器') }}</span><el-button :disabled="busy || !canCreate" @click="newDraft">{{ uiText('新建草稿') }}</el-button></div></template>
          <form @submit.prevent="save">
            <fieldset class="report-design-form" :disabled="busy || locked">
              <div class="report-fields"><label class="report-field"><span>{{ uiText('名称') }}</span><input v-model="form.name" maxlength="120" /></label><label class="report-field"><span>{{ uiText('编码') }}</span><input v-model="form.code" :disabled="Boolean(selected?.id)" maxlength="64" /></label>
                <label class="report-field"><span>{{ uiText('类型') }}</span><select :value="form.kind" :aria-label="uiText('类型')" @change="changeKind"><option value="report">{{ uiText('报表') }}</option><option value="dashboard">{{ uiText('大屏') }}</option></select></label></div>
              <DashboardEditor v-if="board" :key="editorKey" v-model="board" :catalog="catalog" @valid="value => valid = value" />
              <ReportQueryEditor v-else :key="editorKey + '-query'" v-model="query" :catalog="catalog" @valid="value => valid = value" />
            </fieldset>
            <div class="report-actions"><el-button type="primary" :loading="busy" :disabled="locked || !valid" @click="save">{{ uiText('保存草稿') }}</el-button><el-button :disabled="busy || !canPublish || !selected?.id || selected.status !== 'draft' || !valid" @click="publish">{{ uiText('发布') }}</el-button><el-button v-if="selected" :disabled="busy || !canCreate" @click="copyDraft">{{ uiText('复制为新草稿') }}</el-button></div>
            <p v-if="locked">{{ uiText('无编辑权限或定义已发布/归档；有创建权限时可以复制为新草稿。') }}</p>
          </form>
        </el-card>
        <div class="report-run-column">
          <el-card shadow="never">
            <template #header>{{ uiText('已保存报表') }}</template>
            <el-table :data="rows" stripe @row-click="selectRow"><el-table-column prop="name" :label="uiText('名称')" min-width="140" /><el-table-column prop="kind" :label="uiText('类型')" width="100" /><el-table-column prop="status" :label="uiText('状态')" width="110" /><el-table-column :label="uiText('操作')" width="100"><template #default="{ row }"><el-button link type="primary" :disabled="busy || !auth.can('report:execute')" @click.stop="run(row)">{{ uiText('运行') }}</el-button></template></el-table-column></el-table>
            <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next, total" :disabled="busy" @current-change="load" />
            <p v-if="!rows.length && !busy">{{ uiText('暂无数据') }}</p>
          </el-card>
          <el-card v-if="result && running" shadow="never"><ReportViewer :key="running.id + '-' + runRevision" :report="running" :initial="result" :catalog="catalog" /></el-card>
        </div>
      </div>
    </div>
  </AppLayout>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useLatestRead } from '@/composables/useLatestRead'
import { useTenantStore } from '@/stores/tenants'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { errorMessage } from '@/api/request'
import { ElMessage } from 'element-plus'
import { AppLayout } from '@/components'
import { reportsApi, type ReportCatalogItem, type ReportDefinition } from '@/api'
import { asQuery, newReportQuery, type DashboardDesign, type ReportOutput, type ReportQuery } from '@/api/reportTypes'
import DashboardEditor from '@/components/reports/DashboardEditor.vue'
import ReportQueryEditor from '@/components/reports/ReportQueryEditor.vue'
import ReportViewer from '@/components/reports/ReportViewer.vue'
import { uiText } from '@/i18n/uiText'
import '@/styles/report-workbench.css'
const catalog = ref<ReportCatalogItem[]>([]), rows = ref<ReportDefinition[]>([]), selected = ref<ReportDefinition | null>(null)
const result = ref<ReportOutput | null>(null), running = ref<ReportDefinition | null>(null), runRevision = ref(0)
const busy = ref(false), error = ref(''), valid = ref(true), editorKey = ref(0)
const form = reactive<{ name: string; code: string; kind: ReportDefinition['kind']; definition: ReportQuery | DashboardDesign }>({ name: '', code: '', kind: 'report', definition: newReportQuery() })
const board = computed({ get: () => 'widgets' in form.definition ? form.definition as DashboardDesign : undefined, set: value => { if (value) form.definition = value } })
const query = computed({ get: () => form.definition as ReportQuery, set: value => { form.definition = value } })
const auth = useAuthStore()
const administrator = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser))
const canCreate = computed(() => administrator.value && auth.can('report:create'))
const canEdit = computed(() => administrator.value && auth.can(selected.value ? 'report:update' : 'report:create'))
const canPublish = computed(() => administrator.value && auth.can('report:publish'))
const locked = computed(() => !canEdit.value || (!!selected.value && selected.value.status !== 'draft'))
const page = ref(1), total = ref(0)
const tenants = useTenantStore(), modules = useModuleStore()
let contextGeneration = 0
const clearResult = () => { result.value = null; running.value = null }
const beginRead = useLatestRead(() => { rows.value = []; catalog.value = []; total.value = 0; clearResult() })
const beginRun = useLatestRead(clearResult)
const guard = useUnsavedChanges({ source: () => !locked.value ? form : null, busy: () => busy.value, clear: () => { selected.value = null; form.name = ''; form.code = ''; clearResult() } })
watch(() => JSON.stringify([tenants.currentId,modules.config]), () => { contextGeneration++; beginRead(); beginRun(); rows.value = []; catalog.value = []; selected.value = null; clearResult(); Object.assign(form,{ name: '', code: '', kind: 'report', definition: newReportQuery() }); editorKey.value++; guard.markClean(); void load() }, { flush: 'sync' })
function normalized(value: Record<string,unknown>) { if ('widgets' in value) { const design = JSON.parse(JSON.stringify(value)) as DashboardDesign; design.widgets.forEach(x => { x.definition = asQuery(x.definition) }); return design } return asQuery(value) }
function loadEditor(row: ReportDefinition) { selected.value = row; Object.assign(form,{ name: row.name, code: row.code, kind: row.kind, definition: normalized(row.definition) }); editorKey.value++; valid.value = true; guard.markClean() }
async function selectRow(row: ReportDefinition) { if (!busy.value && await guard.confirmDiscard()) loadEditor(row) }
async function newDraft() { if (busy.value || !canCreate.value || !await guard.confirmDiscard()) return; selected.value = null; error.value = ''; Object.assign(form,{ name: '', code: '', kind: 'report', definition: newReportQuery(catalog.value[0]?.key) }); editorKey.value++; valid.value = true; guard.markClean() }
async function copyDraft() { if (busy.value || !canCreate.value || !selected.value || !await guard.confirmDiscard()) return; selected.value = null; form.code = ''; form.name += uiText('副本'); editorKey.value++; guard.markClean() }
function changeKind(event: Event) {
  const element = event.target as HTMLSelectElement
  if (element.value === 'report' && board.value && (board.value.widgets.length > 1 || board.value.filters.length || board.value.links.length)) {
    error.value = uiText('包含多个组件、统一筛选或联动的看板不能直接转换，请新建报表。'); element.value = form.kind; return
  }
  form.kind = element.value as ReportDefinition['kind']
  if (form.kind === 'dashboard' && !board.value) form.definition = { schema_version: 2, widgets: [{ key: 'w1', title: form.name || uiText('新组件'), span: 12, definition: query.value }], filters: [], links: [] }
  else if (form.kind === 'report' && board.value) form.definition = board.value.widgets[0]?.definition || newReportQuery()
  editorKey.value++; valid.value = true
}
function showError(err: unknown) { error.value = errorMessage(err,uiText('操作失败')) }
async function load() { const current = beginRead(); const owner = contextGeneration; try { const [sources,data] = await Promise.all([reportsApi.catalog(),reportsApi.list({ page: page.value, page_size: 20 })]); if (current() && owner === contextGeneration) { catalog.value = sources; rows.value = data.items; total.value = data.pagination.total } } catch (err) { if (current() && owner === contextGeneration) showError(err) } }
async function save(): Promise<boolean> {
  if (busy.value || locked.value || !valid.value) return false
  busy.value = true; error.value = ''; const owner = contextGeneration
  try { const response = selected.value?.id ? await reportsApi.update(selected.value.id,{ name: form.name, kind: form.kind, definition: form.definition, version: selected.value.version }) : await reportsApi.create({ name: form.name, code: form.code, kind: form.kind, definition: form.definition }); if (!guard.isSessionCurrent() || owner !== contextGeneration) return false; loadEditor(response.data.data); ElMessage.success(uiText('已保存')); await load(); return true } catch (err) { if (guard.isSessionCurrent() && owner === contextGeneration) showError(err); return false } finally { busy.value = false }
}
async function publish() {
  if (busy.value || !canPublish.value || selected.value?.status !== 'draft' || !valid.value) return
  if (guard.dirty.value && !await save()) return
  busy.value = true; error.value = ''; const owner = contextGeneration
  try { const response = await reportsApi.publish(selected.value.id,selected.value.version); if (!guard.isSessionCurrent() || owner !== contextGeneration) return; loadEditor(response.data.data); ElMessage.success(uiText('已发布')); await load() } catch (err) { if (guard.isSessionCurrent() && owner === contextGeneration) showError(err) } finally { busy.value = false }
}
async function run(row: ReportDefinition) { if (busy.value || !auth.can('report:execute')) return; const current = beginRun(); const owner = contextGeneration; busy.value = true; error.value = ''; clearResult(); try { const response = await reportsApi.run(row.id); if (current() && owner === contextGeneration) { result.value = response; running.value = row; runRevision.value++ } } catch (err) { if (current() && owner === contextGeneration) showError(err) } finally { busy.value = false } }
onMounted(load)
</script>
