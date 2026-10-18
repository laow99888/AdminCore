<template>
  <div class="report-dashboard-editor">
    <div class="report-section"><strong>{{ uiText('看板组件') }} ({{ design.widgets.length }}/8)</strong><button type="button" class="report-btn" :disabled="design.widgets.length >= 8" @click="addWidget">{{ uiText('添加组件') }}</button></div>
    <p>{{ uiText('组件依次排列；手机自动单列。统一筛选与联动叠加固定筛选，不会替换它。') }}</p>
    <details v-for="(widget,index) in design.widgets" :key="widget.key" class="report-editor-panel" open>
      <summary>{{ index + 1 }}. {{ widget.title }}</summary>
      <div class="report-fields">
        <label class="report-field"><span>{{ uiText('组件名称') }}</span><input v-model="widget.title" maxlength="80" /></label>
        <label class="report-field"><span>{{ uiText('组件宽度') }}</span><select v-model.number="widget.span" :aria-label="uiText('组件宽度')"><option :value="6">{{ uiText('半宽') }}</option><option :value="12">{{ uiText('整宽') }}</option></select></label>
      </div>
      <div class="report-section"><button type="button" class="report-btn" :disabled="index === 0" @click="move(index,-1)">{{ uiText('上移') }}</button><button type="button" class="report-btn" :disabled="index === design.widgets.length - 1" @click="move(index,1)">{{ uiText('下移') }}</button><button type="button" class="report-btn" :disabled="design.widgets.length <= 1" @click="removeWidget(widget.key)">{{ uiText('删除组件') }}</button></div>
      <ReportQueryEditor v-model="widget.definition" :catalog="catalog" @valid="value => validity[widget.key] = value" />
    </details>
    <div class="report-section"><strong>{{ uiText('统一筛选') }}</strong><button type="button" class="report-btn" :disabled="design.filters.length >= 4" @click="addFilter">{{ uiText('添加统一筛选') }}</button></div>
    <fieldset v-for="(filter,index) in design.filters" :key="filter.key" class="report-editor-panel">
      <legend>{{ uiText('统一筛选') }} {{ index + 1 }}</legend>
      <div class="report-fields"><label class="report-field"><span>{{ uiText('筛选名称') }}</span><input v-model="filter.label" maxlength="80" /></label><label class="report-field"><span>{{ uiText('操作符') }}</span><select v-model="filter.operator" :aria-label="uiText('操作符')"><option v-for="op in ['eq','in','gte','lte','contains']" :key="op" :value="op">{{ op }}</option></select></label><ReportValueInput v-model="filter.value" :label="uiText('默认筛选值')" :kind="filterKind(filter)" :operator="filter.operator" @valid="value => validity[filter.key] = value" /></div>
      <div v-for="widget in design.widgets" :key="widget.key" class="report-config-row"><label><input type="checkbox" :checked="!!binding(filter,widget.key)" @change="toggleBinding(filter,widget.key)" /> {{ uiText('应用到') }} {{ widget.title }}</label><label v-if="binding(filter,widget.key)" class="report-field"><span>{{ uiText('绑定字段') }}</span><select v-model="binding(filter,widget.key)!.field" :aria-label="uiText('绑定字段')"><option v-for="field in source(widget.key)?.filters || []" :key="field" :value="field">{{ field }}</option></select></label></div>
      <button type="button" class="report-btn" @click="design.filters.splice(index,1); delete validity[filter.key]">{{ uiText('删除统一筛选') }}</button>
    </fieldset>
    <div class="report-section"><strong>{{ uiText('图表联动') }}</strong><button type="button" class="report-btn" :disabled="design.links.length >= 8 || design.widgets.length < 2" @click="addLink">{{ uiText('添加联动') }}</button></div>
    <div v-for="(link,index) in design.links" :key="index" class="report-editor-panel report-fields">
      <label class="report-field"><span>{{ uiText('来源组件') }}</span><select v-model="link.source" :aria-label="uiText('来源组件')" @change="link.source_field = ''"><option v-for="widget in design.widgets" :key="widget.key" :value="widget.key">{{ widget.title }}</option></select></label>
      <label class="report-field"><span>{{ uiText('来源维度') }}</span><select v-model="link.source_field" :aria-label="uiText('来源维度')"><option value="">{{ uiText('请选择') }}</option><option v-for="field in linkDimensions(link.source)" :key="field" :value="field">{{ field }}</option></select></label>
      <label class="report-field"><span>{{ uiText('目标组件') }}</span><select v-model="link.target" :aria-label="uiText('目标组件')" @change="link.target_field = ''"><option v-for="widget in design.widgets.filter(item => item.key !== link.source)" :key="widget.key" :value="widget.key">{{ widget.title }}</option></select></label>
      <label class="report-field"><span>{{ uiText('目标筛选字段') }}</span><select v-model="link.target_field" :aria-label="uiText('目标筛选字段')"><option value="">{{ uiText('请选择') }}</option><option v-for="field in source(link.target)?.filters || []" :key="field" :value="field">{{ field }}</option></select></label>
      <button type="button" class="report-btn" @click="design.links.splice(index,1)">{{ uiText('删除联动') }}</button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { ReportCatalogItem } from '@/api'
import { newReportQuery, type DashboardDesign, type DashboardFilter } from '@/api/reportTypes'
import { uiText } from '@/i18n/uiText'
import ReportQueryEditor from './ReportQueryEditor.vue'
import ReportValueInput from './ReportValueInput.vue'
const design = defineModel<DashboardDesign>({ required: true })
const props = defineProps<{ catalog: ReportCatalogItem[] }>()
const emit = defineEmits<{ valid: [boolean] }>()
const validity = reactive<Record<string,boolean>>({})
watch(validity, () => emit('valid', !Object.values(validity).includes(false)), { deep: true })
function source(key: string) { const widget = design.value.widgets.find(item => item.key === key); return props.catalog.find(item => item.key === widget?.definition.data_source) }
function uniqueKey(prefix: string, keys: string[]) { let index = 1; while (keys.includes(`${prefix}${index}`)) index++; return `${prefix}${index}` }
function addWidget() { design.value.widgets.push({ key: uniqueKey('w',design.value.widgets.map(x => x.key)), title: uiText('新组件'), span: 6, definition: newReportQuery(props.catalog[0]?.key) }) }
function move(index: number, delta: number) { const widgets = design.value.widgets; [widgets[index], widgets[index+delta]] = [widgets[index+delta], widgets[index]] }
function removeWidget(key: string) { design.value.widgets = design.value.widgets.filter(x => x.key !== key); design.value.links = design.value.links.filter(x => x.source !== key && x.target !== key); design.value.filters.forEach(x => { x.bindings = x.bindings.filter(b => b.widget !== key) }); delete validity[key] }
function binding(filter: DashboardFilter, key: string) { return filter.bindings.find(x => x.widget === key) }
function toggleBinding(filter: DashboardFilter, key: string) { const found = binding(filter,key); if (found) filter.bindings = filter.bindings.filter(x => x !== found); else filter.bindings.push({ widget: key, field: source(key)?.filters[0] || '' }) }
function filterKind(filter: DashboardFilter) { const first = filter.bindings[0]; return first ? source(first.widget)?.field_types?.[first.field] : undefined }
function addFilter() { design.value.filters.push({ key: uniqueKey('f',design.value.filters.map(x => x.key)), label: uiText('新筛选'), operator: 'eq', value: '', bindings: [] }) }
function linkDimensions(key: string) { return design.value.widgets.find(x => x.key === key)?.definition.dimensions.map(x => x.field).filter(field => !['date','datetime'].includes(source(key)?.field_types?.[field] || '')) || [] }
function addLink() { const [first,second] = design.value.widgets; design.value.links.push({ source: first.key, source_field: linkDimensions(first.key)[0] || '', target: second.key, target_field: source(second.key)?.filters[0] || '' }) }
</script>
