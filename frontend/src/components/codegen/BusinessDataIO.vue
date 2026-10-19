<template>
  <div v-if="canImport || canExport" class="business-io">
    <el-button v-if="canImport" :disabled="busy || loading" @click="open">{{ uiText('业务导入') }}</el-button>
    <el-button v-for="format in canExport ? formats : []" :key="format" :disabled="busy || loading" @click="exportRows(format)">{{ uiText('后台导出 {p0}', { p0: format.toUpperCase() }) }}</el-button>
    <section v-if="exportTask && canExport" class="export-status" :aria-label="uiText('后台导出')">
      <p role="status">{{ uiText('后台导出') }}：{{ taskLabel(exportTask.status) }} · {{ exportTask.progress }}% · {{ uiText('总单据数') }} {{ exportTask.result?.documents ?? 0 }} · {{ uiText('展开行数') }} {{ exportTask.result?.rows ?? 0 }}</p>
      <p>{{ uiText('最多10000单、50000展开行、50 MiB，有效24小时。各明细组按序横向对齐；下载时复核当前权限和数据，变化后需重新导出。') }}</p>
      <p v-if="exportTask.status === 'failed' || exportTask.status === 'cancelled'" role="alert">{{ uiText('导出已停止，请检查权限或缩小范围后重新导出；运行中可在任务中心取消。') }}</p>
      <p v-if="exportTask.result?.expires_at">{{ uiText('导出有效期至') }} {{ formatDateTime(exportTask.result.expires_at) }}</p>
      <el-button :disabled="busy" @click="refreshExport">{{ uiText('刷新导出结果') }}</el-button>
      <el-button v-if="exportTask.status === 'success'" :disabled="busy || exportExpired" @click="downloadExport">{{ uiText('下载导出文件') }}</el-button>
    </section>
    <span v-if="error && !opened" role="alert">{{ error }}</span>
    <BaseDialog v-model="opened" :title="uiText('业务导入')" width="760px" :loading="busy" @close="reset">
      <div class="business-io-body">
      <p>{{ uiText(isDocument ? '最多5000源行、10 MiB。相同业务键合成整单；任一明细失败整单不写，其他成功单据保留。' : '最多5000行、10 MiB。先预检，再确认；逐行提交，失败行不会撤销成功行。') }}</p>
      <p v-if="isDocument">{{ uiText('每行重复填写相同主字段；明细使用“组名.字段名”。全空明细组不生成行；更新会替换所有明细组，未映射的可选组会清空。') }}</p>
      <p v-if="error" role="alert" class="io-error">{{ error }}</p>
      <template v-if="catalog && !preview && !task">
        <el-button :disabled="busy" @click="template">{{ uiText('导入模板') }}</el-button>
        <label class="file-label">{{ uiText('选择导入文件') }}<input type="file" accept=".csv,.xlsx" :disabled="busy" @change="selected" /></label>
        <template v-if="headers.length">
          <div class="mapping-tools">
            <label>{{ uiText('个人映射模板') }}<select v-model="mappingId" :aria-label="uiText('个人映射模板')" :disabled="busy" @change="applyMapping"><option value="">{{ uiText('请选择') }}</option><option v-for="item in mappings" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
            <el-button :disabled="busy || !mappingId" @click="removeMapping">{{ uiText('删除模板') }}</el-button>
          </div>
          <div class="column-mapping">
            <label v-for="header in headers" :key="header"><span>{{ header }}</span><select v-model="mapping[header]" :aria-label="uiText('映射列 {p0}', { p0: header })" :disabled="busy"><option value="">{{ uiText('忽略此列') }}</option><option v-for="field in catalog.fields" :key="field.name" :value="field.name">{{ field.label }} ({{ field.name }}){{ field.required ? ' *' : '' }}</option></select></label>
          </div>
          <div class="mapping-tools">
            <label>{{ uiText('唯一业务键') }}<select v-model="key" :aria-label="uiText('唯一业务键')" :disabled="busy"><option value="">{{ uiText('请选择') }}</option><option v-for="field in catalog.fields.filter(item => item.key)" :key="field.name" :value="field.name">{{ field.label }}</option></select></label>
            <label>{{ uiText('重复处理') }}<select v-model="mode" :aria-label="uiText('重复处理')" :disabled="busy"><option v-for="item in catalog.modes" :key="item" :value="item">{{ modeLabel(item) }}</option></select></label>
          </div>
          <p>{{ uiText('必填字段须全部映射；关联与附件使用可访问记录的ID，字典可使用值或唯一标签。') }}</p>
          <div class="mapping-tools"><label>{{ uiText('模板名称') }}<input v-model="mappingName" maxlength="80" :disabled="busy" /></label><el-button :disabled="busy || !valid || !mappingName.trim() || mappings.length >= 20" @click="saveMapping">{{ uiText('保存个人模板') }}</el-button></div>
        </template>
      </template>
      <template v-if="preview || task">
        <p v-if="!task">{{ uiText('预检不会写入业务记录，也不执行业务扩展；确认时仍会复核权限、唯一性和版本。') }}</p>
        <p v-if="task" role="status">{{ uiText('任务状态') }}：{{ taskLabel(task.status) }} · {{ task.progress }}%</p>
        <dl class="summary"><div v-for="item in summaryFields" :key="item.key"><dt>{{ uiText(item.label) }}</dt><dd>{{ summary?.[item.key] ?? 0 }}</dd></div></dl>
        <p v-if="summary?.source_rows !== undefined">{{ uiText('源文件行数') }}：{{ summary.source_rows }}</p>
        <p v-if="task && task.status === 'failed'" role="alert">{{ uiText('任务已停止，已成功的行保留；请到任务中心检查原因并接续。') }}</p>
        <ul v-if="!task && preview?.errors.length" class="errors"><li v-for="item in preview.errors" :key="item.row">{{ uiText('第 {p0} 行', { p0: item.row }) }}：{{ rowError(item.message) }}</li></ul>
        <p v-if="!task && preview">{{ uiText('预检有效期至') }} {{ formatDateTime(preview.expires_at) }}</p>
      </template>
      </div>
      <template #footer><div class="business-io-footer">
        <el-button :disabled="busy" @click="opened = false">{{ uiText('关闭') }}</el-button>
        <el-button v-if="preview && !task" :disabled="busy" @click="preview = null">{{ uiText('返回映射') }}</el-button>
        <el-button v-if="!preview && !task" type="primary" :disabled="busy || !valid" :loading="busy" @click="preflight">{{ uiText('只校验预览') }}</el-button>
        <el-button v-if="preview && !task" type="primary" :disabled="busy || preview.summary.created + preview.summary.updated + preview.summary.skipped === 0" :loading="busy" @click="submit">{{ uiText('确认执行导入') }}</el-button>
        <el-button v-if="task" :disabled="busy" @click="refreshTask">{{ uiText('刷新导入结果') }}</el-button>
        <el-button v-if="task && (task.result.failed ?? 0) > 0" :disabled="busy" @click="errors">{{ uiText('下载错误行') }}</el-button>
        <el-button v-if="!task && preview && preview.summary.failed > 0" :disabled="busy" @click="previewErrors">{{ uiText('下载错误行') }}</el-button>
      </div></template>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { formatDateTime } from '@/utils/dateTime'
import { sessionIdentity } from '@/auth/sessionIdentity'
import './businessMessages'
import { computed, onDeactivated, onScopeDispose, reactive, ref, watch } from 'vue'
import { BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useTenantStore } from '@/stores/tenants'
import { uiText } from '@/i18n/uiText'
import { exportErrorMessage } from '@/api/dataExports'
import { businessDataIO as api, type BusinessTask, type BusinessExportTask, type ImportCatalog, type ImportPreview, type ImportSummary, type MappingOptions, type PersonalMapping } from '@/api/businessDataIO'

const props = withDefaults(defineProps<{ resource: string; structure?: string; filters?: Record<string, string>; loading?: boolean }>(), { structure: 'single', filters: () => ({}), loading: false })
const emit = defineEmits<{ completed: [] }>()
const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore()
const active = computed(() => auth.isAuthenticated && !!auth.user && !auth.user.must_change_password && modules.enabled('data_io') && modules.enabled(props.resource) && auth.can(props.resource + ':read'))
const canImport = computed(() => active.value && auth.can('data_io:import') && auth.can(props.resource + ':create'))
const canExport = computed(() => active.value && ['single', 'master_detail'].includes(props.structure) && auth.can('data_io:export'))
const formats = ['csv', 'xlsx'] as const
const opened = ref(false), busy = ref(false), error = ref(''), catalog = ref<ImportCatalog | null>(null)
const isDocument = computed(() => props.structure === 'master_detail' || catalog.value?.structure === 'master_detail')
const file = ref<File | null>(null), headers = ref<string[]>([]), mapping = reactive<Record<string, string>>({}), key = ref(''), mode = ref('create')
const mappings = ref<PersonalMapping[]>([]), mappingId = ref(''), mappingName = ref(''), preview = ref<ImportPreview | null>(null), task = ref<BusinessTask | null>(null)
const exportTask = ref<BusinessExportTask | null>(null), exportFormat = ref<'csv' | 'xlsx'>('csv')
const exportExpired = computed(() => !!exportTask.value?.result?.expires_at && Date.parse(exportTask.value.result.expires_at) <= Date.now())
const options = (): MappingOptions => ({ mapping: Object.fromEntries(Object.entries(mapping).filter(([, target]) => target)), key: key.value, mode: mode.value })
const valid = computed(() => {
  const selected = Object.values(options().mapping)
  return !!file.value && !!catalog.value && selected.includes(key.value) && new Set(selected).size === selected.length && catalog.value.fields.filter(item => item.required).every(item => selected.includes(item.name))
})
const summaryFields = computed<Array<{ key: keyof ImportSummary; label: string }>>(() => [{ key: 'total', label: isDocument.value ? '总单据数' : '总行数' }, { key: 'created', label: '新增' }, { key: 'updated', label: '更新' }, { key: 'skipped', label: '跳过' }, { key: 'failed', label: '失败' }])
const summary = computed(() => task.value?.result || preview.value?.summary)
const modeLabel = (value: string) => uiText(({ create: '仅新增，已有键报错', skip: '新增，已有键跳过', update: '新增或更新已有键' } as Record<string, string>)[value] || value)
const taskLabel = (value: string) => uiText(({ pending: '等待执行', running: '执行中', success: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[value] || value)
const rowError = (value: string) => uiText(({ empty_business_key: '业务键为空', duplicate_in_file: '文件内业务键重复', business_key_exists: '业务键已存在，请调整重复处理策略', inconsistent_document_fields: '同一单据的主字段不一致', approval_locked: '审批中或已通过的单据不可修改', record_changed: '记录版本已变化，请重新预检' } as Record<string, string>)[value] || '请检查字段类型、必填值和关联权限')
let generation = 0, controller: AbortController | undefined
function reset() {
  generation++; controller?.abort(); controller = undefined; busy.value = false; error.value = ''; opened.value = false
  file.value = null; headers.value = []; catalog.value = null; preview.value = null; task.value = null; mappings.value = []; mappingId.value = ''; mappingName.value = ''; key.value = ''; mode.value = 'create'
  for (const name of Object.keys(mapping)) delete mapping[name]
}
function resetContext() { reset(); exportTask.value = null }
watch([canImport, canExport, () => auth.user?.id, () => sessionIdentity(auth.token), () => JSON.stringify(auth.user?.permissions), () => JSON.stringify(modules.config), () => tenants.currentId, () => props.resource], resetContext, { flush: 'sync' })
onDeactivated(resetContext); onScopeDispose(resetContext)
async function run(work: (signal: AbortSignal, current: () => boolean) => Promise<void>) {
  if (busy.value) return
  const id = ++generation; controller = new AbortController(); busy.value = true; error.value = ''
  const current = () => generation === id && !controller?.signal.aborted
  try { await work(controller.signal, current) }
  catch (reason) { const message = await exportErrorMessage(reason); if (current()) error.value = message || uiText('操作失败，请检查后重试') }
  finally { if (generation === id) { busy.value = false; controller = undefined } }
}
function open() {
  if (!canImport.value || props.loading || busy.value) return
  reset(); opened.value = true
  return run(async (signal, current) => { const [data, saved] = await Promise.all([api.catalog(props.resource, signal), api.mappings(props.resource, signal)]); if (current()) { catalog.value = data; mappings.value = saved } })
}
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  try { const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click() } finally { URL.revokeObjectURL(url) }
}
function template() {
  if (!catalog.value || !canImport.value || busy.value) return
  download(new Blob(['\ufeff' + catalog.value.fields.map(item => item.name).join(',') + '\r\n'], { type: 'text/csv;charset=utf-8' }), props.resource + '-template.csv')
}
function selected(event: Event) {
  const target = event.target as HTMLInputElement, chosen = target.files?.[0]; target.value = ''
  if (!chosen || !canImport.value || busy.value) return
  file.value = null; headers.value = []; preview.value = null
  for (const name of Object.keys(mapping)) delete mapping[name]
  if (!/\.(csv|xlsx)$/i.test(chosen.name) || !chosen.size || chosen.size > 10 * 1024 * 1024) { error.value = uiText('请选择不超过 10 MiB 的 CSV 或 XLSX 文件'); return }
  return run(async (signal, current) => {
    const result = await api.inspect(props.resource, chosen, signal)
    if (!current()) return
    file.value = chosen; headers.value = result.headers
    for (const header of result.headers) mapping[header] = catalog.value?.fields.find(item => item.name === header || item.label === header)?.name || ''
    key.value = catalog.value?.fields.find(item => item.key)?.name || ''
    mappingId.value = ''
  })
}
function applyMapping() {
  const item = mappings.value.find(row => row.id === mappingId.value)
  if (!item || busy.value) return
  for (const header of headers.value) mapping[header] = item.options.mapping[header] || ''
  key.value = item.options.key; mode.value = item.options.mode
}
function saveMapping() {
  if (!valid.value || !mappingName.value.trim() || !canImport.value) return
  return run(async (signal, current) => { const item = await api.save(props.resource, mappingName.value.trim(), options(), signal); if (current()) { mappings.value.push(item); mappingId.value = item.id; mappingName.value = '' } })
}
function removeMapping() {
  if (!mappingId.value || !canImport.value) return
  const id = mappingId.value
  return run(async (signal, current) => { await api.remove(id, signal); if (current()) { mappings.value = mappings.value.filter(item => item.id !== id); mappingId.value = '' } })
}
function preflight() {
  if (!valid.value || !file.value || !canImport.value) return
  const source = file.value
  return run(async (signal, current) => { const value = await api.preview(props.resource, source, options(), signal); if (current()) preview.value = value })
}
function submit() {
  if (!preview.value || !canImport.value) return
  const id = preview.value.id
  return run(async (signal, current) => { const value = await api.submit(id, signal); if (current()) task.value = value })
}
function refreshTask() {
  if (!task.value || !canImport.value) return
  const id = task.value.id
  return run(async (signal, current) => { const value = await api.task(id, signal); if (current()) { task.value = value; emit('completed') } })
}
function errors() {
  if (!task.value || !canImport.value) return
  const id = task.value.id
  return run(async (signal, current) => { const blob = await api.errors(id, signal); if (current()) download(blob, props.resource + '-errors.csv') })
}
function previewErrors() {
  if (!preview.value || !canImport.value) return
  const id = preview.value.id
  return run(async (signal, current) => { const blob = await api.previewErrors(id, signal); if (current()) download(blob, props.resource + '-preview-errors.csv') })
}
function exportRows(format: 'csv' | 'xlsx') {
  if (!canExport.value || props.loading) return
  const filters = { ...props.filters }
  return run(async (signal, current) => { const value = await api.startExport(props.resource, format, filters, signal); if (current()) { exportTask.value = value; exportFormat.value = format } })
}
function refreshExport() {
  if (!exportTask.value || !canExport.value) return
  const id = exportTask.value.id
  return run(async (signal, current) => { const value = await api.exportTask(id, signal); if (current()) exportTask.value = value })
}
function downloadExport() {
  if (!exportTask.value || exportTask.value.status !== 'success' || !canExport.value || exportExpired.value) return
  const id = exportTask.value.id
  return run(async (signal, current) => { const blob = await api.exportDownload(id, signal); if (current()) download(blob, props.resource + '-export.' + exportFormat.value) })
}
</script>

<style scoped>
.business-io, .mapping-tools { display: flex; align-items: end; flex-wrap: wrap; gap: var(--spacing-sm); }
.business-io :deep(.el-button), .business-io-body :deep(.el-button), .business-io-footer :deep(.el-button) { margin: 0; min-height: 44px; }
.business-io-footer { display: flex; flex-wrap: wrap; justify-content: end; gap: var(--spacing-sm); width: 100%; }
.business-io-body label { display: grid; gap: var(--spacing-xs); min-width: 0; }
.business-io-body select, .business-io-body input { box-sizing: border-box; min-height: 44px; width: 100%; max-width: 100%; color: var(--color-text-primary); background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius-sm, 4px); padding: 8px; font: inherit; }
.business-io-body select:focus-visible, .business-io-body input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.file-label, .mapping-tools, .column-mapping { margin-block: var(--spacing-md); }
.column-mapping { display: grid; gap: var(--spacing-sm); max-height: 320px; overflow-y: auto; }
.column-mapping label { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); align-items: center; overflow-wrap: anywhere; }
.summary { display: flex; flex-wrap: wrap; gap: var(--spacing-lg); }
.summary dd { margin: 4px 0; font-weight: 600; font-size: 1.3em; }
.errors { max-height: 200px; overflow: auto; padding-inline-start: 24px; }
.io-error { color: var(--color-danger); overflow-wrap: anywhere; }
.export-status { flex-basis: 100%; min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 600px) { .column-mapping label { grid-template-columns: 1fr; } .mapping-tools > label { width: 100%; } }
</style>
