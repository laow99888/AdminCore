<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="card-header-row"><h2>{{ uiText('组织与数据权限') }}</h2><BaseButton variant="primary" :disabled="referencesFailed || referencesLoading" @click="edit()">{{ uiText('新增') }}</BaseButton></div></template>
      <el-alert :title="uiText('数据范围不替代接口权限；未配置资源范围时保留原访问规则，多个有效角色的范围取并集')" type="info" :closable="false" class="notice" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
      <el-tabs v-model="section" @tab-change="changeSection">
        <el-tab-pane :label="uiText('部门树')" name="departments" />
        <el-tab-pane :label="uiText('人员归属')" name="memberships" />
        <el-tab-pane :label="uiText('角色数据范围')" name="scopes" />
      </el-tabs>
      <el-tree v-if="section === 'departments' && departments.length" :data="departmentTree" node-key="id" :props="{ label: 'label', children: 'children' }" default-expand-all class="department-tree" />
      <BaseTable :key="section" :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }">
          <el-button link type="primary" :disabled="referencesFailed || referencesLoading" @click="edit(row)">{{ uiText('编辑') }}</el-button>
          <el-button v-if="section !== 'scopes'" link type="danger" @click="remove(row)">{{ uiText('删除') }}</el-button>
        </template>
      </BaseTable>
      <BaseButton v-if="referencesFailed" @click="loadReferences">{{ uiText('重新加载选项') }}</BaseButton>
    </BaseCard>
    <BaseDialog v-model="visible" :before-close="formGuard.confirmDiscard" :title="uiText(form.id ? '编辑' : '新增')" :loading="saving" @confirm="save">
      <div v-if="formError" ref="errorSummary" role="alert" tabindex="-1"><el-alert :title="formError" type="error" :closable="false" class="notice" /></div>
      <el-form label-position="top" :disabled="saving">
        <template v-if="section === 'departments'">
          <el-form-item :label="uiText('部门名称')" required><el-input v-model="form.name" maxlength="100" /></el-form-item>
          <el-form-item :label="uiText('上级部门')"><el-select v-model="form.parent" clearable style="width: 100%"><el-option v-for="department in parentOptions" :key="department.id" :label="department.name" :value="department.id" /></el-select></el-form-item>
          <el-form-item :label="uiText('排序')"><el-input-number v-model="form.order" :min="0" /></el-form-item>
          <el-form-item :label="uiText('启用')"><el-switch v-model="form.is_active" /></el-form-item>
        </template>
        <template v-else-if="section === 'memberships'">
          <el-form-item :label="uiText('用户')" required><el-select v-model="form.user" :disabled="!!form.id" filterable remote :remote-method="searchUsers" :loading="usersLoading" style="width: 100%"><el-option v-for="user in userOptions" :key="user.id" :label="user.username" :value="user.id" /></el-select></el-form-item>
          <el-form-item :label="uiText('部门')" required><el-select v-model="form.department" filterable style="width: 100%"><el-option v-for="department in activeDepartments" :key="department.id" :label="department.name" :value="department.id" /></el-select></el-form-item>
        </template>
        <template v-else>
          <el-form-item :label="uiText('角色')" required><el-select v-model="form.role" :disabled="!!form.id" style="width: 100%"><el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item>
          <el-form-item :label="uiText('资源')" required><el-select v-model="form.resource" :disabled="!!form.id" style="width: 100%"><el-option v-for="(label, key) in resources" :key="key" :label="uiText(label)" :value="key" /></el-select></el-form-item>
          <el-form-item :label="uiText('数据范围')" required><el-select v-model="form.scope" style="width: 100%" @change="form.departments = []"><el-option v-for="(label, key) in scopes" :key="key" :label="uiText(label)" :value="key" /></el-select></el-form-item>
          <el-form-item v-if="form.scope === 'custom'" :label="uiText('授权部门')" required><el-select v-model="form.departments" multiple filterable style="width: 100%"><el-option v-for="department in activeDepartments" :key="department.id" :label="department.name" :value="department.id" /></el-select></el-form-item>
        </template>
      </el-form>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { usePageState } from '@/composables/usePageState'
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AppLayout, BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { organizationApi, type DepartmentRow, type OrganizationSection } from '@/api/organization'
import { rolesApi, usersApi } from '@/api'
import { uiText } from '@/i18n/uiText'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const section = ref<OrganizationSection>('departments')
const rows = ref<any[]>([])
const departments = ref<DepartmentRow[]>([])
const roles = ref<Array<{ id: string; name: string }>>([])
const userOptions = ref<Array<{ id: string; username: string }>>([])
const loading = ref(false)
const referencesLoading = ref(false)
const referencesFailed = ref(false)
const usersLoading = ref(false)
const visible = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
useErrorSummary(formError)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
usePageState({ section, page, pageSize })
const form = reactive<any>({})
const formGuard = useUnsavedChanges({ source: () => form, active: () => visible.value, busy: () => saving.value, canEdit: () => !!(auth.user?.is_staff || auth.user?.is_superuser), clear: () => { visible.value = false; for (const key of Object.keys(form)) delete form[key] } })
const modules = useModuleStore()
const resources = computed<Record<string, string>>(() => Object.fromEntries((modules.config?.scope_resources || [{ key: 'user', title: '用户' }, { key: 'file', title: '文件' }, { key: 'task', title: '任务' }, { key: 'log', title: '日志' }]).map(row => [row.key, row.title])))
const scopes: Record<string, string> = { self: '本人', department: '本部门', department_tree: '部门及下级', custom: '自定义部门', all: '全部' }
const activeDepartments = computed(() => departments.value.filter(department => department.is_active))
const parentOptions = computed(() => {
  const excluded = new Set<string>(form.id ? [form.id] : [])
  let changed = true
  while (changed) { changed = false; for (const department of departments.value) if (department.parent && excluded.has(department.parent) && !excluded.has(department.id)) { excluded.add(department.id); changed = true } }
  return activeDepartments.value.filter(department => !excluded.has(department.id))
})
interface TreeNode { id: string; label: string; children: TreeNode[] }
const departmentTree = computed(() => {
  const nodes = new Map<string, TreeNode>(departments.value.map(department => [department.id, { id: department.id, label: department.name + (department.is_active ? '' : ` (${uiText('停用')})`), children: [] }]))
  const roots: TreeNode[] = []
  for (const department of departments.value) {
    const node = nodes.get(department.id)!
    const parent = department.parent ? nodes.get(department.parent) : undefined
    if (parent) parent.children.push(node); else roots.push(node)
  }
  return roots
})
const columns = computed(() => section.value === 'departments' ? [
  { prop: 'name', label: uiText('部门名称'), width: 200 }, { prop: 'is_active', label: uiText('状态'), width: 100, render: (value: boolean) => uiText(value ? '启用' : '停用') },
] : section.value === 'memberships' ? [{ prop: 'username', label: uiText('用户'), width: 180 }, { prop: 'department_name', label: uiText('部门'), width: 180 }] : [
  { prop: 'role_name', label: uiText('角色'), width: 180 }, { prop: 'resource', label: uiText('资源'), width: 100, render: (value: string) => uiText(resources.value[value] || value) },
  { prop: 'scope', label: uiText('数据范围'), width: 180, render: (value: string) => uiText(scopes[value] || value) },
])
let listVersion = 0
watch(section, () => {
  listVersion++
  rows.value = []; total.value = 0; error.value = ''
}, { flush: 'sync' })
async function load() {
  const version = ++listVersion
  const requestedSection = section.value
  loading.value = true; error.value = ''
  try {
    const data = await organizationApi.list(requestedSection, { page: page.value, page_size: pageSize.value })
    if (version !== listVersion || requestedSection !== section.value) return
    rows.value = data.items; total.value = data.pagination.total
  }
  catch { if (version === listVersion) error.value = uiText('组织数据加载失败，请重试') }
  finally { if (version === listVersion) loading.value = false }
}
async function loadReferences() {
  referencesLoading.value = true; referencesFailed.value = false
  try {
    const loaded: DepartmentRow[] = []
    for (let index = 1; ; index++) {
      const data = await organizationApi.list<DepartmentRow>('departments', { page: index, page_size: 100 })
      if (data.pagination.total > 10000) throw new Error('部门数量超过当前选择器范围')
      loaded.push(...data.items)
      if (index >= data.pagination.total_pages) break
    }
    departments.value = loaded
    const loadedRoles: Array<{ id: string; name: string }> = []
    for (let index = 1; ; index++) {
      const data = await rolesApi.list({ page: index, page_size: 100 })
      if (data.pagination.total > 10000) throw new Error('角色数量超过当前选择器范围')
      loadedRoles.push(...data.items)
      if (index >= data.pagination.total_pages) break
    }
    roles.value = loadedRoles
  } catch { referencesFailed.value = true; error.value = uiText('部门或角色选项加载失败，请重新加载') }
  finally { referencesLoading.value = false }
}
let userSearchVersion = 0
async function searchUsers(keyword: string) {
  const version = ++userSearchVersion
  usersLoading.value = true
  try { const data = await usersApi.list({ search: keyword, page_size: 50 }); if (version === userSearchVersion) userOptions.value = data.items }
  catch { formError.value = uiText('用户选项加载失败，请重试') }
  finally { if (version === userSearchVersion) usersLoading.value = false }
}
function changeSection() { page.value = 1; load() }
function changePage(value: number) { page.value = value; load() }
function changeSize(value: number) { pageSize.value = value; page.value = 1; load() }
function edit(row?: any) {
  Object.assign(form, { id: '', name: '', parent: null, order: 0, is_active: true, version: 0, user: '', department: '', role: '', resource: 'user', scope: 'self', departments: [] }, row ? JSON.parse(JSON.stringify(row)) : {})
  formError.value = ''; visible.value = true
  if (section.value === 'memberships') {
    if (row) userOptions.value = [{ id: row.user, username: row.username }]
    else searchUsers('')
  }
}
async function save() {
  if (saving.value || !(auth.user?.is_staff || auth.user?.is_superuser)) return
  formError.value = ''
  let data: object
  if (section.value === 'departments') {
    if (!form.name.trim()) { formError.value = uiText('请填写部门名称'); return }
    data = { name: form.name, parent: form.parent || null, order: form.order, is_active: form.is_active, version: form.version }
  } else if (section.value === 'memberships') {
    if (!form.user || !form.department) { formError.value = uiText('请选择用户和部门'); return }
    data = { user: form.user, department: form.department, version: form.version }
  } else {
    if (!form.role || (form.scope === 'custom' && !form.departments.length)) { formError.value = uiText('请选择角色和授权范围'); return }
    data = { role: form.role, resource: form.resource, scope: form.scope, departments: form.departments, version: form.version }
  }
  saving.value = true; formError.value = ''
  try { await organizationApi.save(section.value, form.id, data); visible.value = false; ElMessage.success(uiText('保存成功')); await load(); await loadReferences() }
  catch (exception: any) { formError.value = uiText(exception?.response?.status === 409 ? '内容已被其他人修改，已保留输入，请重新打开编辑窗口' : '保存失败，已保留输入') }
  finally { saving.value = false }
}
async function remove(row: any) {
  try { await ElMessageBox.confirm(uiText('删除前请确认关联数据已调整'), uiText('确认'), { type: 'warning' }) } catch { return }
  try { await organizationApi.remove(section.value, row.id); await load(); await loadReferences() }
  catch { error.value = uiText('删除失败，请检查关联数据') }
}
onMounted(() => { load(); loadReferences() })
onBeforeUnmount(() => { listVersion++ })
</script>

<style scoped>
h2 { margin: 0; font-size: var(--font-size-lg); }
.notice { margin-bottom: var(--spacing-md); }
.department-tree { margin-bottom: var(--spacing-lg); max-height: 280px; overflow: auto; }
</style>
