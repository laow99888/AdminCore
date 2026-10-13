<template>
  <div class="person-picker">
    <el-button :disabled="disabled" @click="open">{{ modelValue ? `${modelValue.display_name} (${modelValue.username})` : uiText('选择人员') }}</el-button>
    <el-button v-if="modelValue" link :disabled="disabled" @click="emit('update:modelValue', null)">{{ uiText('清除选择') }}</el-button>
  </div>
  <Teleport to="body">
    <BaseDialog v-model="visible" :title="uiText('选择人员')" width="760px" :confirm-disabled="busy || !candidate" @confirm="confirm">
      <div class="picker-search">
        <el-input v-model="search" :aria-label="uiText('搜索姓名或用户名')" :placeholder="uiText('搜索姓名或用户名')" maxlength="100" clearable @keyup.enter="searchPeople" />
        <el-button :disabled="busy" @click="searchPeople">{{ uiText('搜索') }}</el-button>
      </div>
      <div class="picker-grid">
        <aside :aria-label="uiText('部门筛选')">
          <el-button size="small" :disabled="busy" @click="chooseDepartment('')">{{ uiText('全部可选人员') }}</el-button>
          <p v-if="departmentsBusy" role="status">{{ uiText('正在加载部门') }}</p>
          <div v-else-if="departmentError" role="alert"><p>{{ uiText('部门加载失败，可继续搜索人员') }}</p><el-button size="small" @click="loadDepartments">{{ uiText('重试') }}</el-button></div>
          <p v-else-if="!departments.enabled">{{ uiText('组织模块未启用') }}</p>
          <p v-else-if="!departments.items.length">{{ uiText('没有可见部门') }}</p>
          <el-tree v-else :data="tree" node-key="id" :props="{ label: 'name' }" default-expand-all highlight-current :current-node-key="department" @node-click="clickDepartment" />
          <p v-if="departments.truncated" role="status">{{ uiText('部门列表已截断，请使用人员搜索') }}</p>
        </aside>
        <section :aria-label="uiText('可选人员')" :aria-busy="busy">
          <p v-if="busy" role="status">{{ uiText('正在加载人员') }}</p>
          <div v-else-if="error" role="alert"><p>{{ uiText('人员加载失败，请重试') }}</p><el-button @click="loadPeople">{{ uiText('重试') }}</el-button></div>
          <p v-else-if="!people.length" role="status">{{ uiText('没有匹配的人员，请调整搜索或部门') }}</p>
          <el-radio-group v-else v-model="candidateId" :aria-label="uiText('可选人员')" class="people-list">
            <el-radio v-for="person in people" :key="person.id" :value="person.id" class="person-option">
              <span class="person-label">{{ person.display_name }} ({{ person.username }})<small>{{ person.department_name || uiText('未分配部门') }}</small></span>
            </el-radio>
          </el-radio-group>
          <el-pagination v-if="total > 0" :current-page="page" :page-size="10" :total="total" :disabled="busy" :pager-count="5" layout="prev, pager, next" @current-change="changePage" />
        </section>
      </div>
    </BaseDialog>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BaseDialog from './BaseDialog.vue'
import { personnelApi, type Person, type PersonnelPurpose, type PickerDepartments } from '@/api/personnel'
import { uiText } from '@/i18n/uiText'
const props = withDefaults(defineProps<{ modelValue: Person | null; purpose: PersonnelPurpose; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ 'update:modelValue': [person: Person | null] }>()
const visible = ref(false), busy = ref(false), departmentsBusy = ref(false), error = ref(false), departmentError = ref(false)
const search = ref(''), appliedSearch = ref(''), department = ref(''), page = ref(1), total = ref(0), candidateId = ref('')
const people = ref<Person[]>([]), departments = ref<PickerDepartments>({ enabled: false, truncated: false, items: [] })
const candidate = computed(() => people.value.find(person => person.id === candidateId.value))
type Node = PickerDepartments['items'][number] & { children: Node[] }
const tree = computed(() => {
  const nodes = new Map<string, Node>(departments.value.items.map(row => [row.id, { ...row, children: [] }]))
  const roots: Node[] = []
  for (const node of nodes.values()) { const parent = node.parent && nodes.get(node.parent); if (parent) parent.children.push(node); else roots.push(node) }
  return roots
})
let controller: AbortController | undefined, departmentController: AbortController | undefined
async function loadPeople() {
  controller?.abort(); const current = new AbortController(); controller = current
  busy.value = true; error.value = false; candidateId.value = ''; people.value = []; total.value = 0
  try {
    const data = await personnelApi.people(props.purpose, { search: appliedSearch.value, ...(department.value ? { department: department.value } : {}), page: page.value, page_size: 10 }, current.signal)
    if (!current.signal.aborted) { people.value = data.items; total.value = data.pagination.total }
  } catch { if (!current.signal.aborted) error.value = true }
  finally { if (!current.signal.aborted) busy.value = false }
}
async function loadDepartments() {
  departmentController?.abort(); const current = new AbortController(); departmentController = current
  departmentsBusy.value = true; departmentError.value = false
  try { const data = await personnelApi.departments(props.purpose, current.signal); if (!current.signal.aborted) departments.value = data }
  catch { if (!current.signal.aborted) departmentError.value = true }
  finally { if (!current.signal.aborted) departmentsBusy.value = false }
}
function searchPeople() { appliedSearch.value = search.value.trim(); page.value = 1; void loadPeople() }
function chooseDepartment(id: string) { department.value = id; page.value = 1; void loadPeople() }
function clickDepartment(node: Node) { chooseDepartment(node.id) }
function changePage(value: number) { page.value = value; void loadPeople() }
function open() {
  search.value = ''; appliedSearch.value = ''; department.value = ''; page.value = 1; visible.value = true
  departments.value = { enabled: false, truncated: false, items: [] }
  void loadDepartments(); void loadPeople()
}
function confirm() { if (!busy.value && candidate.value) { emit('update:modelValue', candidate.value); visible.value = false } }
function cancelRequests() { controller?.abort(); departmentController?.abort(); busy.value = false; departmentsBusy.value = false }
watch(visible, value => { if (!value) cancelRequests() })
watch(() => props.disabled, value => { if (value) visible.value = false })
onBeforeUnmount(cancelRequests)
</script>

<style scoped>
.person-picker, .picker-search { display: flex; gap: var(--spacing-sm); min-width: 0; }
.person-picker { flex-wrap: wrap; }
.person-picker :deep(.el-button) { max-width: 100%; height: auto; min-height: 32px; white-space: normal; }
.picker-search { margin-bottom: var(--spacing-md); }
.picker-grid { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: var(--spacing-md); }
aside, section { min-width: 0; }
aside { border-right: 1px solid var(--color-border); padding-right: var(--spacing-sm); }
.people-list { display: flex; flex-direction: column; align-items: stretch; width: 100%; }
.person-option { height: auto; min-height: 48px; margin: 0; padding: var(--spacing-sm) 0; }
.person-label { display: block; white-space: normal; overflow-wrap: anywhere; }
.person-label small { display: block; color: var(--color-text-secondary); }
:deep(.el-radio__label) { min-width: 0; }
:deep(.el-tree-node__label) { overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 640px) { .picker-grid { grid-template-columns: minmax(0, 1fr); } aside { max-height: 150px; overflow-y: auto; border-right: 0; border-bottom: 1px solid var(--color-border); padding-bottom: var(--spacing-sm); } }
</style>
