<template>
  <div class="report-result">
    <p v-if="comparison" role="status">{{ uiText('本期 {p0} 至 {p1}（结束日期不含当日）', { p0: comparison.start, p1: comparison.end }) }}</p>
    <p v-if="result.truncated" role="status">{{ uiText('结果组达到上限，请缩小筛选范围；下方不是完整汇总。') }}</p>
    <BaseChart v-if="result.definition.chart_type !== 'table'" :option="chartOption" :height="300" :caption="caption" :table="{ headers: headers, rows: result.rows.map(row => result.columns.map(column => cell(column,row[column]))) }" @select="index => emit('select',result.rows[index])" />
    <div class="report-table-scroll"><table class="result"><caption>{{ caption }}</caption><thead><tr><th v-for="(column,index) in result.columns" :key="column" scope="col">{{ headers[index] }}</th><th scope="col">{{ uiText('操作') }}</th></tr></thead><tbody><tr v-for="(row,index) in result.rows" :key="index"><td v-for="column in result.columns" :key="column">{{ cell(column,row[column]) }}</td><td><div class="report-actions"><button type="button" class="report-btn" :disabled="busy" @click="emit('details',row)">{{ uiText('查看明细') }}</button><button v-for="field in linkFields || []" :key="field" type="button" class="report-btn" :disabled="busy || row[field] == null" @click="emit('select',row,field)">{{ linkFields!.length > 1 ? uiText('联动 {p0}',{ p0: field }) : uiText('联动筛选') }}</button></div></td></tr><tr v-if="!result.rows.length"><td :colspan="result.columns.length + 1">{{ uiText('暂无数据') }}</td></tr></tbody></table></div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import BaseChart from '@/components/common/BaseChart.vue'
import { displayReportCell, type ReportResult } from '@/api/reportTypes'
import { uiText } from '@/i18n/uiText'
import './deepeningMessages'
const props = defineProps<{ result: ReportResult; caption: string; busy: boolean; linkFields?: string[] }>()
const emit = defineEmits<{ select: [row: Record<string,unknown>, field?: string]; details: [row: Record<string,unknown>] }>()
const cell = (column: string, value: unknown) => displayReportCell(props.result,column,value)
const headers = computed(() => props.result.columns.map(key => props.result.column_labels?.[key] || key))
const comparison = computed(() => props.result.definition.comparison as { start: string; end: string } | undefined)
const chartOption = computed<EChartsOption>(() => {
  const query = props.result.definition
  const dimensions = (query.dimensions || []) as Array<{ field: string }>
  const metrics = props.result.chart_columns || props.result.columns.filter(key => !dimensions.some(x => x.field === key))
  const labels = props.result.rows.map(row => dimensions.length ? dimensions.map(x => String(row[x.field] ?? '')).join(' / ') : uiText('合计'))
  if (query.chart_type === 'pie') return { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: '60%', data: labels.map((name,index) => ({ name, value: Number(props.result.rows[index][metrics[0]] || 0) })) }] }
  return { tooltip: { trigger: 'axis' }, legend: { type: 'scroll', top: 0, left: 0, right: 0 }, grid: { top: 50, left: 50, right: 20, bottom: 40 }, xAxis: { type: 'category', data: labels }, yAxis: { type: 'value' },
    series: metrics.map(key => ({ name: props.result.column_labels?.[key] || key, type: query.chart_type === 'bar' ? 'bar' : 'line', data: props.result.rows.map(row => row[key] == null ? null : Number(row[key])), ...(query.chart_type === 'area' ? { areaStyle: {} } : {}) })) }
})
</script>
