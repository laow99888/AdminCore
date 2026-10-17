<template>
  <AppLayout>
    <el-row :gutter="16">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never">
          <template #header><div class="builder-header"><span>{{ uiText('报表构建器') }}</span><el-button :disabled="busy" @click="newDraft">{{ uiText('新建草稿') }}</el-button></div></template>
          <el-alert v-if="error" :title="error" type="error" :closable="false" />
          <el-form label-position="top" :disabled="busy || selected?.status === 'published' || selected?.status === 'archived'">
            <el-form-item :label="uiText('名称')"><el-input v-model="form.name" /></el-form-item>
            <el-form-item :label="uiText('编码')"><el-input v-model="form.code" :disabled="Boolean(selected?.id)" /></el-form-item>
            <el-form-item :label="uiText('类型')"><el-radio-group v-model="form.kind"><el-radio value="report">{{ uiText('报表') }}</el-radio><el-radio value="dashboard">{{ uiText('大屏') }}</el-radio></el-radio-group></el-form-item>
            <el-form-item :label="uiText('数据源')"><el-select v-model="form.definition.data_source" @change="resetFields"><el-option v-for="item in catalog" :key="item.key" :label="item.label" :value="item.key" /></el-select></el-form-item>
            <el-form-item :label="uiText('图表')"><el-select v-model="form.definition.chart_type"><el-option v-for="kind in ['table','bar','line','pie','area']" :key="kind" :label="kind" :value="kind" /></el-select></el-form-item>
            <el-form-item :label="uiText('维度')"><el-select v-model="dimension" clearable @change="setDimension"><el-option v-for="field in currentSource?.dimensions || []" :key="field" :label="field" :value="field" /></el-select></el-form-item>
            <el-form-item :label="uiText('指标')"><el-select v-model="form.definition.metric.field"><el-option v-for="field in currentSource?.metrics || []" :key="field" :label="field" :value="field" /></el-select></el-form-item>
            <el-form-item :label="uiText('聚合')"><el-select v-model="form.definition.metric.aggregation"><el-option label="count" value="count" /><el-option label="sum" value="sum" /><el-option label="avg" value="avg" /></el-select></el-form-item>
            <el-form-item><el-button type="primary" :loading="busy" @click="save">{{ uiText('保存草稿') }}</el-button><el-button :disabled="busy || !selected?.id || selected.status !== 'draft'" @click="publish">{{ uiText('发布') }}</el-button></el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="16">
        <el-card shadow="never">
          <template #header>{{ uiText('已保存报表') }}</template>
          <el-table :data="rows" stripe @row-click="selectRow"><el-table-column prop="name" :label="uiText('名称')" /><el-table-column prop="kind" :label="uiText('类型')" width="100" /><el-table-column prop="status" :label="uiText('状态')" width="110" /><el-table-column :label="uiText('操作')" width="100"><template #default="{ row }"><el-button link type="primary" :disabled="busy" @click.stop="run(row)">{{ uiText('运行') }}</el-button></template></el-table-column></el-table>
          <BaseChart v-if="result && result.definition.chart_type !== 'table'" :option="chartOption" :height="340" :caption="uiText('报表图表')" :table="{ headers: result.columns, rows: result.rows.map(row => result!.columns.map(column => toCellValue(row[column]))) }" />
          <el-table v-if="result" :data="result.rows" class="result"><el-table-column v-for="column in result.columns" :key="column" :prop="column" :label="column" /></el-table>
        </el-card>
      </el-col>
    </el-row>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { AppLayout } from '@/components'
import BaseChart from '@/components/common/BaseChart.vue'
import type { EChartsOption } from 'echarts'
import { reportsApi, type ReportCatalogItem, type ReportDefinition } from '@/api'
import { uiText } from '@/i18n/uiText'

const catalog = ref<ReportCatalogItem[]>([])
const rows = ref<ReportDefinition[]>([])
const selected = ref<ReportDefinition | null>(null)
const result = ref<{ columns: string[]; rows: Array<Record<string, unknown>>; definition: Record<string, unknown> } | null>(null)
const busy = ref(false)
const error = ref('')
const dimension = ref('')
type ReportChartType = 'table' | 'bar' | 'line' | 'pie' | 'area'
type ReportAggregation = 'count' | 'sum' | 'avg'
interface ReportBuilderDefinition extends Record<string, unknown> {
  data_source: string
  chart_type: ReportChartType
  dimensions: Array<{ field: string }>
  metric: { field: string; aggregation: ReportAggregation }
  filters: Array<Record<string, unknown>>
  limit: number
}
interface ReportForm {
  name: string
  code: string
  kind: ReportDefinition['kind']
  definition: ReportBuilderDefinition
}
const form = reactive<ReportForm>({ name: '', code: '', kind: 'report', definition: { data_source: 'tasks', chart_type: 'table', dimensions: [], metric: { field: 'id', aggregation: 'count' }, filters: [], limit: 100 } })
const currentSource = computed(() => catalog.value.find(item => item.key === form.definition.data_source))
const chartOption = computed<EChartsOption>(() => {
  const rows = result.value?.rows || []
  const columns = result.value?.columns || []
  const labels = rows.map(row => columns[0] === 'value' ? uiText('合计') : String(row[columns[0]] ?? ''))
  const values = rows.map(row => Number(row.value || 0))
  const type = result.value?.definition.chart_type
  const chartType = type === 'area' ? 'line' : type
  if (chartType === 'pie') return { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: '60%', data: labels.map((name, index) => ({ name, value: values[index] })) }] }
  return { tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: labels }, yAxis: { type: 'value' }, series: [{ type: chartType as 'bar' | 'line', data: values, ...(type === 'area' ? { areaStyle: {} } : {}) }] }
})
function resetFields() { form.definition.dimensions = []; dimension.value = ''; form.definition.metric.field = currentSource.value?.metrics[0] || 'id' }
function setDimension(value: string) { form.definition.dimensions = value ? [{ field: value }] : [] }
function toCellValue(value: unknown): string | number { return typeof value === 'string' || typeof value === 'number' ? value : value == null ? '' : String(value) }
function loadEditor(row: ReportDefinition) { selected.value = row; const definition = JSON.parse(JSON.stringify(row.definition)) as ReportBuilderDefinition; Object.assign(form, { name: row.name, code: row.code, kind: row.kind, definition }); dimension.value = definition.dimensions?.[0]?.field || '' }
function selectRow(row: ReportDefinition) { if (!busy.value) loadEditor(row) }
function newDraft() { if (busy.value) return; selected.value = null; dimension.value = ''; error.value = ''; Object.assign(form, { name: '', code: '', kind: 'report', definition: { data_source: 'tasks', chart_type: 'table', dimensions: [], metric: { field: 'id', aggregation: 'count' }, filters: [], limit: 100 } }) }
function showError(err: unknown) { error.value = err instanceof Error ? err.message : uiText('操作失败') }
async function load() { try { catalog.value = await reportsApi.catalog(); rows.value = (await reportsApi.list({ page_size: 100 })).items } catch (err) { showError(err) } }
async function save() { if (busy.value || (selected.value && selected.value.status !== 'draft')) return; busy.value = true; error.value = ''; try { const response = selected.value?.id ? await reportsApi.update(selected.value.id, { name: form.name, kind: form.kind, definition: form.definition }) : await reportsApi.create({ name: form.name, code: form.code, kind: form.kind, definition: form.definition }); loadEditor(response.data.data); ElMessage.success(uiText('已保存')); await load() } catch (err) { showError(err) } finally { busy.value = false } }
async function publish() { if (busy.value || selected.value?.status !== 'draft') return; busy.value = true; error.value = ''; try { const response = await reportsApi.publish(selected.value.id); loadEditor(response.data.data); ElMessage.success(uiText('已发布')); await load() } catch (err) { showError(err) } finally { busy.value = false } }
async function run(row: ReportDefinition) { if (busy.value) return; busy.value = true; error.value = ''; result.value = null; try { result.value = await reportsApi.run(row.id) } catch (err) { showError(err) } finally { busy.value = false } }
onMounted(load)
</script>

<style scoped>.result { margin-top: 16px }.builder-header { display: flex; align-items: center; justify-content: space-between; gap: 8px }</style>
