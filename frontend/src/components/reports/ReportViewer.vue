<template>
  <section class="report-viewer" :aria-label="report.name" :aria-busy="busy">
    <h2>{{ report.name }}</h2>
    <p v-if="error" role="alert">{{ error }}</p>
    <form v-if="design" class="report-fields" @submit.prevent="refresh">
      <ReportValueInput v-for="filter in design.filters" :key="filter.key" v-model="filters[filter.key]" :label="filter.label" :operator="filter.operator" :kind="filterKind(filter.key)" :disabled="busy" @valid="value => validity[filter.key] = value" />
      <div class="report-actions"><button type="submit" class="report-btn" :disabled="busy || !valid">{{ uiText('应用筛选并刷新') }}</button><button type="button" class="report-btn" :disabled="busy" @click="reset">{{ uiText('恢复默认筛选') }}</button><button v-if="selection" type="button" class="report-btn" :disabled="busy" @click="selection = undefined; refresh()">{{ uiText('清除联动') }}</button></div>
    </form>
    <button v-else type="button" class="report-btn" :disabled="busy" @click="refresh">{{ uiText('刷新报表') }}</button>
    <p v-if="selection" role="status">{{ uiText('当前联动') }}：{{ selection.field }} = {{ displayValue(selection.value) }}</p>
    <p v-if="busy" role="status">{{ uiText('加载中') }}</p>
    <div v-if="output && 'widgets' in output" class="report-widget-grid">
      <article v-for="widget in output.widgets" :key="widget.key" class="report-widget" :style="{ gridColumn: `span ${widget.span}` }">
        <h3>{{ widget.title }}</h3><ReportResultTable :result="widget.result" :caption="widget.title" :busy="busy" :link-fields="[...new Set(design?.links.filter(x => x.source === widget.key).map(x => x.source_field))]" @select="(row,field) => select(widget.key,row,field)" @details="row => details(widget.key,widget.result,row)" />
      </article>
    </div>
    <ReportResultTable v-else-if="output" :result="output" :caption="report.name" :busy="busy" @details="row => details('single',output as ReportResult,row)" />
    <BaseDialog v-model="detailsOpen" :title="uiText('报表明细')" width="900px" :loading="detailBusy">
      <div class="report-dialog-body"><p v-if="detailError" role="alert">{{ detailError }}</p><p>{{ uiText('明细按当前权限重新查询；时间比较仅下钻本期。每行对应一条主记录，明细指标显示该记录的汇总。') }}</p>
        <div v-if="detailResult" class="report-table-scroll"><table><thead><tr><th v-for="column in detailResult.columns" :key="column" scope="col">{{ detailResult.column_labels?.[column] || column }}</th></tr></thead><tbody><tr v-for="(row,index) in detailResult.rows" :key="index"><td v-for="column in detailResult.columns" :key="column">{{ displayValue(row[column]) }}</td></tr><tr v-if="!detailResult.rows.length"><td :colspan="detailResult.columns.length">{{ uiText('暂无数据') }}</td></tr></tbody></table></div>
      </div>
      <template #footer><div class="report-actions"><el-button :disabled="detailBusy || detailPage <= 1" @click="loadDetails(detailPage-1)">{{ uiText('上一页') }}</el-button><span>{{ detailPage }}</span><el-button :disabled="detailBusy || !detailResult?.has_more || detailPage >= 100" @click="loadDetails(detailPage+1)">{{ uiText('下一页') }}</el-button><el-button :disabled="detailBusy" @click="detailsOpen = false">{{ uiText('关闭') }}</el-button></div></template>
    </BaseDialog>
  </section>
</template>
<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { reportsApi, type ReportCatalogItem, type ReportDefinition } from '@/api'
import { displayValue, type DashboardDesign, type ReportOutput, type ReportResult, type ReportRunOptions, type ReportDetails } from '@/api/reportTypes'
import { errorMessage } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
import BaseDialog from '@/components/common/BaseDialog.vue'
import ReportResultTable from './ReportResultTable.vue'
import ReportValueInput from './ReportValueInput.vue'
import { uiText } from '@/i18n/uiText'
import './deepeningMessages'
const props = defineProps<{ report: ReportDefinition; initial: ReportOutput; catalog: ReportCatalogItem[] }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const output = ref<ReportOutput | null>(props.initial)
const design = computed(() => 'widgets' in props.initial ? props.initial.definition as DashboardDesign : null)
const filters = reactive<Record<string,unknown>>({}), validity = reactive<Record<string,boolean>>({})
const selection = ref<ReportRunOptions['selection']>(), busy = ref(false), error = ref('')
const appliedOptions = ref<ReportRunOptions>()
const valid = computed(() => !Object.values(validity).includes(false))
let generation = 0, active = true, controller: AbortController | undefined
const detailsOpen = ref(false), detailBusy = ref(false), detailError = ref(''), detailPage = ref(1), detailResult = ref<ReportDetails | null>(null)
let detailGeneration = 0, detailController: AbortController | undefined, detailRequest: { widget: string; group: Record<string,unknown>; options?: ReportRunOptions } | undefined
function cancel() { generation++; detailGeneration++; controller?.abort(); detailController?.abort(); output.value = null; detailResult.value = null; detailsOpen.value = false; busy.value = false; detailBusy.value = false }
watch(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password, tenants.currentId, modules.config]), cancel, { flush: 'sync' })
onScopeDispose(() => { active = false; cancel() })
function defaults() { Object.keys(filters).forEach(key => delete filters[key]); design.value?.filters.forEach(item => { filters[item.key] = JSON.parse(JSON.stringify(item.value)) }); Object.keys(validity).forEach(key => delete validity[key]); selection.value = undefined }
watch(() => props.initial, value => { cancel(); output.value = value; defaults(); appliedOptions.value = options() }, { immediate: true })
function filterKind(key: string) { const first = design.value?.filters.find(x => x.key === key)?.bindings[0]; const widget = design.value?.widgets.find(x => x.key === first?.widget); return props.catalog.find(x => x.key === widget?.definition.data_source)?.field_types?.[first?.field || ''] }
function options(): ReportRunOptions | undefined { return design.value ? { filters: JSON.parse(JSON.stringify(filters)), ...(selection.value ? { selection: { ...selection.value } } : {}) } : undefined }
async function refresh() {
  if (busy.value || !valid.value) return
  cancel(); const current = ++generation; controller = new AbortController(); busy.value = true; error.value = ''
  const submitted = options()
  try { const response = await reportsApi.run(props.report.id, submitted, controller.signal); if (active && current === generation) { output.value = response; appliedOptions.value = submitted } }
  catch (err) { if (active && current === generation) error.value = errorMessage(err,uiText('操作失败')) }
  finally { if (active && current === generation) busy.value = false }
}
function reset() { defaults(); void refresh() }
function select(widget: string, row: Record<string,unknown>, field?: string) { const link = design.value?.links.find(x => x.source === widget && (!field || x.source_field === field)); if (!link || !row || row[link.source_field] == null || busy.value) return; selection.value = { widget, field: link.source_field, value: row[link.source_field] }; void refresh() }
function details(widget: string, result: ReportResult, row: Record<string,unknown>) { const dimensions = (result.definition.dimensions || []) as Array<{ field: string }>; detailRequest = { widget, group: Object.fromEntries(dimensions.map(x => [x.field,row[x.field]])), options: appliedOptions.value }; detailsOpen.value = true; void loadDetails(1) }
async function loadDetails(page: number) {
  if (!detailRequest || detailBusy.value) return
  const current = ++detailGeneration; detailController?.abort(); detailController = new AbortController(); detailBusy.value = true; detailError.value = ''; detailResult.value = null
  try { const response = await reportsApi.details(props.report.id, { ...detailRequest, page, page_size: 20 },detailController.signal); if (active && current === detailGeneration) { detailResult.value = response; detailPage.value = page } }
  catch (err) { if (active && current === detailGeneration) { output.value = null; detailError.value = errorMessage(err,uiText('操作失败')) } }
  finally { if (active && current === detailGeneration) detailBusy.value = false }
}
</script>
