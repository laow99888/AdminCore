<template>
  <AppLayout>
    <el-row :gutter="16">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never">
          <template #header>{{ uiText('报表构建器') }}</template>
          <el-form label-position="top">
            <el-form-item :label="uiText('名称')"><el-input v-model="form.name" /></el-form-item>
            <el-form-item :label="uiText('编码')"><el-input v-model="form.code" :disabled="Boolean(selected?.id)" /></el-form-item>
            <el-form-item :label="uiText('类型')"><el-radio-group v-model="form.kind"><el-radio value="report">{{ uiText('报表') }}</el-radio><el-radio value="dashboard">{{ uiText('大屏') }}</el-radio></el-radio-group></el-form-item>
            <el-form-item :label="uiText('数据源')"><el-select v-model="form.definition.data_source" @change="resetFields"><el-option v-for="item in catalog" :key="item.key" :label="item.label" :value="item.key" /></el-select></el-form-item>
            <el-form-item :label="uiText('图表')"><el-select v-model="form.definition.chart_type"><el-option v-for="kind in ['table','bar','line','pie','area']" :key="kind" :label="kind" :value="kind" /></el-select></el-form-item>
            <el-form-item :label="uiText('维度')"><el-select v-model="dimension" clearable @change="setDimension"><el-option v-for="field in currentSource?.dimensions || []" :key="field" :label="field" :value="field" /></el-select></el-form-item>
            <el-form-item :label="uiText('指标')"><el-select v-model="form.definition.metric.field"><el-option v-for="field in currentSource?.metrics || []" :key="field" :label="field" :value="field" /></el-select></el-form-item>
            <el-form-item :label="uiText('聚合')"><el-select v-model="form.definition.metric.aggregation"><el-option label="count" value="count" /><el-option label="sum" value="sum" /><el-option label="avg" value="avg" /></el-select></el-form-item>
            <el-form-item><el-button type="primary" :loading="busy" @click="save">{{ uiText('保存草稿') }}</el-button><el-button :disabled="!selected?.id || selected.status !== 'draft'" @click="publish">{{ uiText('发布') }}</el-button></el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="16">
        <el-card shadow="never">
          <template #header>{{ uiText('已保存报表') }}</template>
          <el-table :data="rows" stripe @row-click="selectRow"><el-table-column prop="name" :label="uiText('名称')" /><el-table-column prop="kind" :label="uiText('类型')" width="100" /><el-table-column prop="status" :label="uiText('状态')" width="110" /><el-table-column :label="uiText('操作')" width="100"><template #default="{ row }"><el-button link type="primary" @click.stop="run(row)">{{ uiText('运行') }}</el-button></template></el-table-column></el-table>
          <BaseChart v-if="result && form.definition.chart_type !== 'table'" :option="chartOption" :height="340" caption="报表图表" :table="{ headers: result.columns, rows: result.rows.map(row => result!.columns.map(column => row[column])) }" />
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
const result = ref<{ columns: string[]; rows: Array<Record<string, any>> } | null>(null)
const busy = ref(false)
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
  const labels = rows.map(row => String(row[columns[0]] ?? '合计'))
  const values = rows.map(row => Number(row.value || 0))
  const chartType = form.definition.chart_type === 'area' ? 'line' : form.definition.chart_type
  if (chartType === 'pie') return { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: '60%', data: labels.map((name, index) => ({ name, value: values[index] })) }] }
  return { tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: labels }, yAxis: { type: 'value' }, series: [{ type: chartType as 'bar' | 'line', data: values, ...(form.definition.chart_type === 'area' ? { areaStyle: {} } : {}) }] }
})
function resetFields() { form.definition.dimensions = []; dimension.value = ''; form.definition.metric.field = currentSource.value?.metrics[0] || 'id' }
function setDimension(value: string) { form.definition.dimensions = value ? [{ field: value }] : [] }
function selectRow(row: ReportDefinition) { selected.value = row; Object.assign(form, { name: row.name, code: row.code, kind: row.kind, definition: JSON.parse(JSON.stringify(row.definition)) as ReportBuilderDefinition }); dimension.value = row.definition.dimensions?.[0]?.field || '' }
async function load() { catalog.value = await reportsApi.catalog(); rows.value = (await reportsApi.list({ page_size: 100 })).items; resetFields() }
async function save() { busy.value = true; try { const response = selected.value?.id ? await reportsApi.update(selected.value.id, { name: form.name, kind: form.kind, definition: form.definition }) : await reportsApi.create({ name: form.name, code: form.code, kind: form.kind, definition: form.definition }); selected.value = response.data.data; ElMessage.success(uiText('已保存')); await load() } finally { busy.value = false } }
async function publish() { if (!selected.value) return; await reportsApi.publish(selected.value.id); ElMessage.success(uiText('已发布')); await load() }
async function run(row: ReportDefinition) { result.value = await reportsApi.run(row.id) }
onMounted(load)
</script>

<style scoped>.result { margin-top: 16px }</style>
