<template>
  <div class="report-query">
    <div class="report-fields">
      <label class="report-field"><span>{{ uiText('数据源') }}</span><select v-model="query.data_source" :aria-label="uiText('数据源')" @change="resetSource"><option v-for="item in catalog" :key="item.key" :value="item.key">{{ item.label }}</option></select></label>
      <label class="report-field"><span>{{ uiText('图表') }}</span><select v-model="query.chart_type" :aria-label="uiText('图表')"><option v-for="kind in ['table','bar','line','pie','area']" :key="kind" :value="kind">{{ kind }}</option></select></label>
      <label class="report-field"><span>{{ uiText('结果组上限') }}</span><input v-model.number="query.limit" type="number" min="1" max="100" /></label>
    </div>
    <div class="report-section"><strong>{{ uiText('维度') }}</strong><button type="button" class="report-btn" :disabled="query.dimensions.length >= 2 || !source?.dimensions.length" @click="addDimension">{{ uiText('添加维度') }}</button></div>
    <div v-for="(item, index) in query.dimensions" :key="index" class="report-config-row">
      <label class="report-field"><span>{{ uiText('维度字段') }}</span><select v-model="item.field" :aria-label="uiText('维度字段')" @change="delete item.grain"><option v-for="field in source?.dimensions || []" :key="field" :value="field">{{ field }}</option></select></label>
      <label v-if="isDate(item.field)" class="report-field"><span>{{ uiText('日期粒度') }}</span><select v-model="item.grain" :aria-label="uiText('日期粒度')"><option v-for="grain in grains" :key="grain" :value="grain">{{ grain }}</option></select></label>
      <button type="button" class="report-btn" :aria-label="uiText('删除维度 {p0}', { p0: index + 1 })" @click="query.dimensions.splice(index,1)">{{ uiText('删除') }}</button>
    </div>
    <div class="report-section"><strong>{{ uiText('指标') }}</strong><button type="button" class="report-btn" :disabled="(query.metrics?.length || 0) >= 4" @click="addMetric">{{ uiText('添加指标') }}</button></div>
    <p v-if="source?.metrics.some(field => field.includes('.'))">{{ uiText('带点号的指标来自登记的明细数值字段，与主表分别汇总，避免重复累计主表金额。') }}</p>
    <div v-for="(item, index) in query.metrics" :key="item.key" class="report-config-row">
      <label class="report-field"><span>{{ uiText('名称') }}</span><input v-model="item.label" maxlength="80" /></label>
      <label class="report-field"><span>{{ uiText('指标字段') }}</span><select v-model="item.field" :aria-label="uiText('指标字段')" @change="item.aggregation = item.field === 'id' ? 'count' : 'sum'"><option v-for="field in source?.metrics || []" :key="field" :value="field">{{ field }}</option></select></label>
      <label class="report-field"><span>{{ uiText('聚合') }}</span><select v-model="item.aggregation" :aria-label="uiText('聚合')"><option v-for="kind in item.field === 'id' ? ['count'] : ['sum','avg']" :key="kind" :value="kind">{{ kind }}</option></select></label>
      <button type="button" class="report-btn" :disabled="query.metrics!.length <= 1" :aria-label="uiText('删除指标 {p0}', { p0: index + 1 })" @click="query.metrics!.splice(index,1)">{{ uiText('删除') }}</button>
    </div>
    <div class="report-section"><strong>{{ uiText('时间比较') }}</strong></div>
    <div class="report-fields">
      <label class="report-field"><span>{{ uiText('时间比较') }}</span><select :value="query.comparison?.mode || ''" :aria-label="uiText('时间比较')" @change="changeComparison(($event.target as HTMLSelectElement).value)"><option value="">{{ uiText('不比较') }}</option><option value="previous_period" :disabled="!dateFields.length">{{ uiText('环比（上期等长）') }}</option><option value="previous_year" :disabled="!dateFields.length">{{ uiText('同比（上年同日）') }}</option></select></label>
      <template v-if="query.comparison">
        <label class="report-field"><span>{{ uiText('比较日期字段') }}</span><select v-model="query.comparison.field" :aria-label="uiText('比较日期字段')"><option v-for="field in dateFields" :key="field" :value="field">{{ field }}</option></select></label>
        <label class="report-field"><span>{{ uiText('开始日期（含）') }}</span><input v-model="query.comparison.start" type="date" :aria-label="uiText('开始日期（含）')" /></label>
        <label class="report-field"><span>{{ uiText('结束日期（不含）') }}</span><input v-model="query.comparison.end" type="date" :aria-label="uiText('结束日期（不含）')" /></label>
      </template>
    </div>
    <p v-if="query.comparison">{{ uiText('比较按本地时区的日期区间统计，最多366天；使用非日期分类维度。变化率基期为0时留空。') }}</p>
    <p v-if="!comparisonValid" role="alert">{{ uiText('请填写有效比较区间，移除日期维度、饼图和同日期字段的固定筛选。') }}</p>
    <div class="report-section"><strong>{{ uiText('固定筛选') }}</strong><button type="button" class="report-btn" :disabled="query.filters.length >= 6 || !source?.filters.length" @click="addFilter">{{ uiText('添加筛选') }}</button></div>
    <div v-for="(item, index) in query.filters" :key="index" class="report-config-row">
      <label class="report-field"><span>{{ uiText('筛选字段') }}</span><select v-model="item.field" :aria-label="uiText('筛选字段')" @change="resetFilter(index)"><option v-for="field in source?.filters || []" :key="field" :value="field">{{ field }}</option></select></label>
      <label class="report-field"><span>{{ uiText('操作符') }}</span><select v-model="item.operator" :aria-label="uiText('操作符')"><option v-for="op in operators" :key="op" :value="op">{{ op }}</option></select></label>
      <ReportValueInput v-model="item.value" :label="uiText('筛选值')" :kind="source?.field_types?.[item.field]" :operator="item.operator" @valid="value => validity[index] = value" />
      <button type="button" class="report-btn" :aria-label="uiText('删除筛选 {p0}', { p0: index + 1 })" @click="removeFilter(index)">{{ uiText('删除') }}</button>
    </div>
    <p v-if="query.chart_type === 'pie' && query.metrics!.length > 1" role="alert">{{ uiText('饼图只支持一个指标') }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { ReportCatalogItem } from '@/api'
import { newReportQuery, type ReportQuery } from '@/api/reportTypes'
import { uiText } from '@/i18n/uiText'
import ReportValueInput from './ReportValueInput.vue'
import './deepeningMessages'
const query = defineModel<ReportQuery>({ required: true })
const props = defineProps<{ catalog: ReportCatalogItem[] }>()
const emit = defineEmits<{ valid: [boolean] }>()
const source = computed(() => props.catalog.find(item => item.key === query.value.data_source))
const dateFields = computed(() => source.value?.filters.filter(isDate) || [])
const comparisonValid = computed(() => {
  const item = query.value.comparison
  if (!item) return true
  const start = Date.parse(item.start), end = Date.parse(item.end), days = (end-start)/86400000
  return dateFields.value.includes(item.field) && /^\d{4}-\d{2}-\d{2}$/.test(item.start) && /^\d{4}-\d{2}-\d{2}$/.test(item.end)
    && Number.isFinite(days) && new Date(start).toISOString().slice(0,10) === item.start && new Date(end).toISOString().slice(0,10) === item.end
    && days >= 1 && days <= 366 && ['previous_period','previous_year'].includes(item.mode) && query.value.chart_type !== 'pie'
    && !query.value.dimensions.some(item => isDate(item.field)) && !query.value.filters.some(filter => filter.field === item.field)
})
const grains = ['day','week','month','quarter','year'] as const
const operators = ['eq','in','gte','lte','contains']
const validity = reactive<Record<number, boolean>>({})
watch(() => [Object.values(validity), query.value.chart_type, query.value.metrics?.length, comparisonValid.value], () => emit('valid', comparisonValid.value && !Object.values(validity).includes(false) && !(query.value.chart_type === 'pie' && query.value.metrics!.length > 1)), { deep: true, immediate: true })
function changeComparison(mode: string) { if (!mode) delete query.value.comparison; else if (dateFields.value.length) query.value.comparison = { field: dateFields.value[0], mode: mode as 'previous_period' | 'previous_year', start: query.value.comparison?.start || '', end: query.value.comparison?.end || '' } }
function resetSource() { query.value = newReportQuery(query.value.data_source); Object.keys(validity).forEach(key => delete validity[Number(key)]) }
function isDate(field: string) { return ['date','datetime'].includes(source.value?.field_types?.[field] || '') }
function addDimension() { const field = source.value?.dimensions.find(field => !query.value.dimensions.some(item => item.field === field)); if (field) query.value.dimensions.push({ field, ...(isDate(field) ? { grain: 'day' } : {}) }) }
function addMetric() { let index = 1; while (query.value.metrics!.some(item => item.key === `m_value_${index}`)) index++; query.value.metrics!.push({ key: `m_value_${index}`, label: uiText('合计'), field: 'id', aggregation: 'count' }) }
function initialValue(field: string) { return source.value?.field_types?.[field] === 'boolean' ? true : source.value?.field_types?.[field] === 'integer' ? 0 : '' }
function addFilter() { const field = source.value?.filters[0]; if (field) query.value.filters.push({ field, operator: 'eq', value: initialValue(field) }) }
function resetFilter(index: number) { const filter = query.value.filters[index]; filter.value = initialValue(filter.field); filter.operator = 'eq' }
function removeFilter(index: number) { query.value.filters.splice(index,1); const remaining = Object.entries(validity).filter(([key]) => Number(key) !== index); Object.keys(validity).forEach(key => delete validity[Number(key)]); remaining.forEach(([key,value]) => { validity[Number(key) > index ? Number(key)-1 : Number(key)] = value }) }
</script>
