<template>
  <BaseCard class="appointments">
    <template #header><div class="appointment-toolbar"><h2>{{ uiText('主兼职任职与历史') }}</h2><el-button type="primary" :disabled="!administrator || busy || !referencesReady" @click="open('create')">{{ uiText('新增任职') }}</el-button></div></template>
    <el-alert :closable="false" type="info" :title="uiText('任职用于主管审批；人员归属仍控制原数据范围，兼职不会自动增加数据权限。结束日期当天已不任职。')" />
    <form class="appointment-toolbar filters" @submit.prevent="applyFilters">
      <label>{{ uiText('搜索任职') }}<input v-model="search" maxlength="100" /></label>
      <label>{{ uiText('有效日期') }}<input v-model="asOf" type="date" /></label>
      <el-button native-type="submit" :disabled="loading">{{ uiText('查询') }}</el-button>
      <el-button :disabled="loading" @click="resetFilters">{{ uiText('全部历史') }}</el-button>
    </form>
    <div v-if="error" role="alert"><el-alert :title="error" type="error" :closable="false" /><el-button :disabled="loading" @click="load">{{ uiText('重试') }}</el-button></div>
    <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="20" :action-width="isMobile ? 100 : 190" @update:currentPage="changePage">
      <template #actions="{ row }"><el-button link :disabled="!administrator || busy || row.cancelled" @click="open('end', row)">{{ uiText('结束任期') }}</el-button><el-button link :disabled="!administrator || busy || row.status !== 'planned'" @click="open('cancel', row)">{{ uiText('取消计划') }}</el-button></template>
    </BaseTable>
    <BaseDialog v-model="visible" :before-close="guard.confirmDiscard" :title="uiText(operation === 'create' ? '新增任职' : operation === 'end' ? '结束任期' : '取消计划')" :loading="busy" :confirm-disabled="!administrator || (operation === 'create' && !referencesReady)" @confirm="save">
      <p v-if="formError" role="alert">{{ formError }}</p>
      <p v-if="operation === 'create'">{{ uiText('首次登记主职任期后，主管审批不再回退旧人员归属；请先补齐当前主职。') }}</p>
      <fieldset :disabled="busy || !administrator" class="appointment-form">
        <template v-if="operation === 'create'">
          <div><span>{{ uiText('任职人员') }}</span><PersonPicker v-model="person" purpose="post" :disabled="busy || !administrator" /></div>
          <label>{{ uiText('任职部门') }}<select v-model="form.department" :aria-label="uiText('任职部门')"><option value="">{{ uiText('请选择部门') }}</option><option v-for="department in departments.filter(item => item.is_active)" :key="department.id" :value="department.id">{{ department.name }}</option></select></label>
          <label>{{ uiText('任职类型') }}<select v-model="form.kind" :aria-label="uiText('任职类型')"><option value="primary">{{ uiText('主职') }}</option><option value="secondary">{{ uiText('兼职') }}</option></select></label>
          <label>{{ uiText('生效日期') }}<input v-model="form.starts_on" type="date" /></label>
        </template>
        <p v-else>{{ selected?.username }} · {{ selected?.department_name }} · {{ selected?.starts_on }}</p>
        <label v-if="operation !== 'cancel'">{{ uiText('结束日期（不含当天）') }}<input v-model="form.ends_on" type="date" /></label>
        <label>{{ uiText('任职变更原因') }}<textarea v-model="form.reason" maxlength="500" rows="3" /></label>
      </fieldset>
    </BaseDialog>
  </BaseCard>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import BaseCard from './BaseCard.vue'
import BaseTable from './BaseTable.vue'
import BaseDialog from './BaseDialog.vue'
import PersonPicker from './PersonPicker.vue'
import { appointmentsApi, type AppointmentRow, type DepartmentRow } from '@/api/organization'
import type { Person } from '@/api/personnel'
import { errorMessage, responseStatus } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
import { useLatestRead } from '@/composables/useLatestRead'
import { useSidebar } from '@/composables/useSidebar'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { uiText } from '@/i18n/uiText'

const props = defineProps<{ departments: DepartmentRow[]; referencesReady: boolean }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const { isMobile } = useSidebar()
const administrator = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser))
const rows = ref<AppointmentRow[]>([]), page = ref(1), total = ref(0), search = ref(''), asOf = ref('')
const loading = ref(false), busy = ref(false), visible = ref(false), error = ref(''), formError = ref('')
const selected = ref<AppointmentRow | null>(null), operation = ref<'create' | 'end' | 'cancel'>('create'), person = ref<Person | null>(null)
const today = () => dayjs().format('YYYY-MM-DD')
const form = reactive({ department: '', kind: 'primary' as AppointmentRow['kind'], starts_on: today(), ends_on: '', reason: '' })
let applied = { search: '', as_of: '' }, generation = 0
const clearDialog = () => { visible.value = false; person.value = null; selected.value = null }
const clear = () => { rows.value = []; total.value = 0; clearDialog() }
const beginRead = useLatestRead(clear)
const guard = useUnsavedChanges({ source: () => ({ ...form, person: person.value?.id }), active: () => visible.value, busy: () => busy.value, canEdit: () => administrator.value, clear: clearDialog })
watch(() => JSON.stringify([tenants.currentId, modules.config]), () => { generation++; beginRead(); clear(); search.value = ''; asOf.value = ''; applied = { search: '', as_of: '' }; page.value = 1; void load() }, { flush: 'sync' })
const columns = computed(() => [
  { prop: 'username', label: uiText('用户'), width: 130 }, { prop: 'department_name', label: uiText('任职部门'), width: 150 },
  { prop: 'kind', label: uiText('任职类型'), width: 100, render: (value: string) => uiText(value === 'primary' ? '主职' : '兼职') },
  { prop: 'starts_on', label: uiText('生效日期'), width: 130 }, { prop: 'ends_on', label: uiText('结束日期（不含当天）'), width: 170 },
  { prop: 'status', label: uiText('状态'), width: 110, render: (value: AppointmentRow['status']) => uiText({ cancelled: '已取消', planned: '未生效', ended: '已结束', active: '生效中' }[value]) },
  { prop: 'reason', label: uiText('任职变更原因'), width: 180 },
])
async function load() { const current = beginRead(); loading.value = true; error.value = ''; try { const data = await appointmentsApi.list({ page: page.value, page_size: 20, ...(applied.search ? { search: applied.search } : {}), ...(applied.as_of ? { as_of: applied.as_of } : {}) }); if (current()) { rows.value = data.items; total.value = data.pagination.total } } catch (err) { if (current()) error.value = errorMessage(err, uiText('任职加载失败')) } finally { if (current()) loading.value = false } }
function applyFilters() { page.value = 1; applied = { search: search.value, as_of: asOf.value }; void load() }
function resetFilters() { search.value = ''; asOf.value = ''; applyFilters() }
function changePage(value: number) { page.value = value; void load() }
function open(kind: typeof operation.value, row?: AppointmentRow) {
  if (busy.value || !administrator.value || (kind === 'create' && !props.referencesReady)) return
  operation.value = kind; selected.value = row || null; person.value = null
  Object.assign(form, { department: '', kind: 'primary', starts_on: today(), ends_on: '', reason: '' })
  formError.value = ''; visible.value = true; guard.markClean()
}
async function save() {
  if (busy.value || !administrator.value || (operation.value === 'create' && !props.referencesReady)) return
  if (!form.reason.trim() || (operation.value === 'create' && (!person.value || !form.department || !form.starts_on)) || (operation.value === 'end' && !form.ends_on)) { formError.value = uiText('请填写人员、部门、日期和变更原因'); return }
  const owner = generation; busy.value = true; formError.value = ''
  try {
    if (operation.value === 'create') await appointmentsApi.create({ user: person.value!.id, ...form, ends_on: form.ends_on || null, version: 0 })
    else await appointmentsApi.finish(selected.value!.id, operation.value, { version: selected.value!.version, reason: form.reason, ...(operation.value === 'end' ? { ends_on: form.ends_on } : {}) })
    if (!guard.isCurrent() || owner !== generation) return
    visible.value = false; ElMessage.success(uiText('已保存')); await load()
  } catch (err) { if (guard.isCurrent() && owner === generation) formError.value = responseStatus(err) === 409 ? uiText('任职已变化，请关闭窗口并刷新后重试，输入已保留') : errorMessage(err, uiText('操作失败，输入已保留')) }
  finally { busy.value = false }
}
onMounted(load)
</script>
<style scoped>
.appointments { margin-top: var(--spacing-lg); }
h2 { margin: 0; font-size: var(--font-size-lg); }
.appointment-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.appointment-toolbar h2 { flex: 1; }
.filters { margin: 16px 0; align-items: end; }
label, .appointment-form { display: grid; gap: 8px; min-width: 0; }
.appointment-form { border: 0; padding: 0; gap: 16px; }
input, select, textarea { font: inherit; color: var(--el-text-color-primary); background: var(--el-fill-color-blank); border: 1px solid var(--el-border-color); border-radius: 6px; min-height: 44px; min-width: 0; padding: 8px; width: 100%; box-sizing: border-box; }
.filters :deep(button) { min-height: 44px; }
@media (max-width: 600px) { .filters label { width: 100%; } }
@media (max-width: 768px) {
  .appointments :deep(.action-buttons) { flex-direction: column; align-items: flex-end; gap: 0; }
  .appointments :deep(.action-buttons .el-button + .el-button) { margin-left: 0; }
}
</style>
