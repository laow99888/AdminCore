<template>
  <section class="query-workbench" :aria-label="uiText('高级查询与方案')">
    <details>
      <summary>{{ uiText('高级查询与方案') }}</summary>
      <div class="query-toolbar">
        <label>{{ uiText('查询方案') }}
          <select v-model="selectedId" :aria-label="uiText('查询方案')" :disabled="busy || disabled" @change="choose">
            <option value="">{{ uiText('不使用方案') }}</option>
            <option v-for="item in saved" :key="item.id" :value="item.id">{{ item.name }}{{ item.shared ? ' · ' + uiText('共享') : '' }}{{ item.available === false ? ' · ' + uiText('已失效') : '' }}</option>
          </select>
        </label>
        <el-button :loading="busy" :disabled="disabled || busy" @click="reload(false)">{{ uiText('刷新方案') }}</el-button>
      </div>
      <p v-if="unavailable" role="status">{{ uiText('部分方案因字段权限或业务结构变化不可用，请联系方案所有者重建') }}</p>
      <p v-if="persistenceError" role="status">{{ uiText('浏览器无法保存方案选择；服务端方案仍可使用') }}</p>
      <label>{{ uiText('条件匹配') }}
        <select v-model="advanced.match" :disabled="disabled || busy" :aria-label="uiText('条件匹配')">
          <option value="all">{{ uiText('全部满足') }}</option><option value="any">{{ uiText('任一满足') }}</option>
        </select>
      </label>
      <div v-for="(item, index) in advanced.conditions" :key="index" class="condition-row">
        <label>{{ uiText('条件字段') }} {{ index + 1 }}
          <select v-model="item.field" :aria-label="uiText('条件字段') + ' ' + (index + 1)" :disabled="disabled || busy" @change="item.op = 'eq'; item.value = ''">
            <option v-for="field in fields" :key="field.name" :value="field.name">{{ uiText(field.label) }}</option>
          </select>
        </label>
        <label>{{ uiText('运算符') }} {{ index + 1 }}
          <select v-model="item.op" :aria-label="uiText('运算符') + ' ' + (index + 1)" :disabled="disabled || busy">
            <option v-for="op in queryOperators(fieldFor(item.field))" :key="op" :value="op">{{ operatorLabel(op) }}</option>
          </select>
        </label>
        <label>{{ uiText('条件值') }} {{ index + 1 }}
          <select v-if="fieldFor(item.field)?.kind === 'boolean'" v-model="item.value" :aria-label="uiText('条件值') + ' ' + (index + 1)" :disabled="disabled || busy">
            <option value="true">{{ uiText('是') }}</option><option value="false">{{ uiText('否') }}</option>
          </select>
          <select v-else-if="fieldFor(item.field)?.kind === 'enum'" v-model="item.value" :aria-label="uiText('条件值') + ' ' + (index + 1)" :disabled="disabled || busy">
            <option v-for="choice in fieldFor(item.field)?.choices" :key="choice.value" :value="choice.value">{{ uiText(choice.label) }}</option>
          </select>
          <input v-else v-model="item.value" :aria-label="uiText('条件值') + ' ' + (index + 1)" :disabled="disabled || busy" maxlength="200" />
        </label>
        <el-button :disabled="disabled || busy" :aria-label="uiText('删除条件') + ' ' + (index + 1)" @click="advanced.conditions.splice(index, 1)">{{ uiText('删除条件') }}</el-button>
      </div>
      <p class="query-help">{{ uiText('高级条件与上方基础筛选同时生效；关联、附件和字典条件使用原始ID或值。最多10个条件。') }}</p>
      <p class="query-help">{{ uiText('保存方案使用已应用的基础筛选、当前高级条件和排序；修改上方筛选后请先搜索。树表仍在当前父节点范围内查询。') }}</p>
      <div class="query-toolbar">
        <el-button :disabled="disabled || busy || !fields.length || advanced.conditions.length >= 10" @click="add">{{ uiText('添加条件') }}</el-button>
        <el-button type="primary" :disabled="disabled || busy" @click="apply">{{ uiText('应用高级条件') }}</el-button>
        <el-button :disabled="disabled || busy" @click="clear">{{ uiText('清空高级条件') }}</el-button>
      </div>
      <div class="query-toolbar">
        <label>{{ uiText('方案名称') }}<input v-model="name" :aria-label="uiText('方案名称')" maxlength="80" :disabled="disabled || busy" /></label>
        <label v-if="administrator"><input v-model="shared" type="checkbox" :disabled="disabled || busy" />{{ uiText('共享给当前范围内有业务读取权限的用户') }}</label>
        <el-button :disabled="disabled || busy || !name.trim()" @click="save(false)">{{ uiText('另存为新方案') }}</el-button>
        <el-button v-if="selected?.editable" :disabled="disabled || busy || !name.trim()" @click="save(true)">{{ uiText('更新方案') }}</el-button>
        <el-button v-if="selected?.editable" type="danger" :disabled="disabled || busy" @click="remove">{{ uiText('删除方案') }}</el-button>
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="notice" role="status">{{ notice }}</p>
    </details>
  </section>
</template>
<script setup lang="ts">
import './workbenchMessages'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import request, { type ApiResponse, errorMessage } from '@/api/request'
import { uiText } from '@/i18n/uiText'
import type { GeneratedField } from './types'
import { emptyAdvanced, queryOperators, type QueryDefinition, type SavedQuery } from './queryTypes'

const props = defineProps<{ endpoint: string; fields: GeneratedField[]; current: QueryDefinition; owner: string; administrator: boolean; disabled?: boolean }>()
const emit = defineEmits<{ apply: [definition: QueryDefinition] }>()
const saved = ref<SavedQuery[]>([]), selectedId = ref(''), name = ref(''), shared = ref(false), busy = ref(false)
const error = ref(''), notice = ref(''), unavailable = ref(0), persistenceError = ref(false)
const advanced = reactive(emptyAdvanced())
const selected = computed(() => saved.value.find(item => item.id === selectedId.value))
const storageKey = computed(() => 'admincore.query-view.v1.' + encodeURIComponent(props.owner))
const fieldFor = (key: string) => props.fields.find(item => item.name === key)
const operatorLabel = (op: string) => uiText(({ eq: '等于', ne: '不等于', contains: '包含', gte: '大于等于', lte: '小于等于' } as Record<string, string>)[op] || op)
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
let alive = true
const controller = new AbortController()
watch(() => props.current.advanced, value => Object.assign(advanced, clone(value)), { immediate: true, deep: true })
watch(() => props.fields.map(field => field.name).join(','), () => {
  const known = new Set(props.fields.map(field => field.name))
  if (advanced.conditions.some(item => !known.has(item.field))) {
    Object.assign(advanced, emptyAdvanced()); selectedId.value = ''; remember()
    notice.value = uiText('查询权限已变化，已清空条件，请重新筛选'); emit('apply', definition())
  }
})
function remember() {
  try { if (selectedId.value) localStorage.setItem(storageKey.value, selectedId.value); else localStorage.removeItem(storageKey.value) }
  catch { persistenceError.value = true }
}
function choose() {
  remember(); error.value = ''; notice.value = ''
  if (!selected.value) { name.value = ''; shared.value = false; emit('apply', { filters: {}, advanced: emptyAdvanced(), ordering: '' }); return }
  name.value = selected.value.name; shared.value = props.administrator && selected.value.shared
  if (selected.value.available === false) { notice.value = uiText('方案已失效，未应用；可删除或重建后更新'); return }
  emit('apply', clone(selected.value.definition))
}
function definition(): QueryDefinition { return { ...clone(props.current), advanced: clone(advanced) } }
function add() { if (props.fields[0] && advanced.conditions.length < 10) advanced.conditions.push({ field: props.fields[0].name, op: 'eq', value: '' }) }
function apply() { selectedId.value = ''; remember(); emit('apply', definition()) }
function clear() { Object.assign(advanced, emptyAdvanced()); apply() }
async function reload(restore: boolean) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const result = await request.get<ApiResponse<{ items: SavedQuery[]; unavailable: number }>>(props.endpoint + 'query-views/', { signal: controller.signal })
    if (!alive) return
    saved.value = result.data.data.items; unavailable.value = result.data.data.unavailable
    if (restore) {
      try { selectedId.value = localStorage.getItem(storageKey.value) || '' } catch { persistenceError.value = true }
      if (selected.value) choose(); else { selectedId.value = ''; remember() }
    } else if (selectedId.value && !selected.value) { selectedId.value = ''; remember() }
  } catch (failure) { if (alive) error.value = errorMessage(failure, uiText('方案加载失败，请重试')) }
  finally { if (alive) busy.value = false }
}
async function save(update: boolean) {
  if (busy.value || props.disabled || !name.value.trim()) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await request.post<ApiResponse<SavedQuery>>(props.endpoint + 'query-views/', {
      ...(update && selected.value ? { id: selected.value.id, version: selected.value.version } : {}),
      name: name.value.trim(), shared: shared.value, definition: definition(),
    }, { signal: controller.signal })
    if (!alive) return
    const row = result.data.data
    saved.value = [...saved.value.filter(item => item.id !== row.id), row]; selectedId.value = row.id
    name.value = row.name; shared.value = row.shared; remember(); emit('apply', clone(row.definition)); notice.value = uiText('查询方案已保存')
  } catch (failure) { if (alive) error.value = errorMessage(failure, uiText('方案保存失败，输入已保留')) }
  finally { if (alive) busy.value = false }
}
async function remove() {
  if (busy.value || props.disabled || !selected.value?.editable) return
  try { await ElMessageBox.confirm(uiText('确定删除该查询方案？'), uiText('提示')) } catch { return }
  if (!alive || props.disabled || !selected.value) return
  busy.value = true; error.value = ''
  try {
    await request.delete(props.endpoint + 'query-views/', { data: { id: selected.value.id, version: selected.value.version }, signal: controller.signal })
    if (!alive) return
    saved.value = saved.value.filter(item => item.id !== selectedId.value); selectedId.value = ''; remember(); notice.value = uiText('查询方案已删除')
  } catch (failure) { if (alive) error.value = errorMessage(failure, uiText('方案删除失败，请刷新后重试')) }
  finally { if (alive) busy.value = false }
}
onBeforeUnmount(() => { alive = false; controller.abort(); saved.value = [] })
void reload(true)
</script>
<style scoped>
.query-workbench { border: 1px solid var(--el-border-color); border-radius: var(--radius-md); padding: 12px; margin: 12px 0; }
summary { cursor: pointer; min-height: 32px; }
.query-toolbar, .condition-row { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin: 12px 0; }
label { display: grid; gap: 6px; max-width: 100%; }
label:has(input[type=checkbox]) { display: flex; align-items: center; align-self: center; }
input, select { box-sizing: border-box; min-width: 0; max-width: 100%; min-height: 40px; border: 1px solid var(--el-border-color); border-radius: 4px; padding: 6px 10px; color: var(--el-text-color-primary); background: var(--el-bg-color); font: inherit; }
input[type=checkbox] { min-height: auto; }
input:focus-visible, select:focus-visible, summary:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.query-help { color: var(--el-text-color-secondary); }
[role=alert] { color: var(--el-color-danger); }
@media(max-width: 640px) { .condition-row > label, .query-toolbar > label { width: 100%; } .query-workbench :deep(button) { min-height: 44px; margin-left: 0; } input, select { min-height: 44px; } }
</style>
