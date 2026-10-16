<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="header"><h2>{{ uiText('特性开关') }}</h2><BaseButton v-if="auth.can('feature_flag:create')" :disabled="busy" @click="edit()">{{ uiText('新增开关') }}</BaseButton></div></template>
      <p>{{ uiText('开关控制功能投放，原有权限仍然生效。关闭开关会立即停止投放。') }}</p>
      <div class="filters"><el-input v-model="search" :aria-label="uiText('搜索开关标识或名称')" :placeholder="uiText('搜索开关标识或名称')" maxlength="100" @keyup.enter="searchRows" /><BaseButton :disabled="busy" @click="searchRows">{{ uiText('搜索') }}</BaseButton><BaseButton :disabled="busy" @click="loadRows">{{ uiText('刷新') }}</BaseButton></div>
      <p v-if="loadError" role="alert">{{ uiText('加载失败，请重试') }}</p>
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-actions="canManage" @update:current-page="changePage" @update:page-size="changePageSize">
        <template #actions="{ row }"><el-button v-if="auth.can('feature_flag:update')" link :disabled="busy" @click="edit(row)">{{ uiText('编辑') }}</el-button><el-button v-if="auth.can('feature_flag:delete')" link type="danger" :disabled="busy" @click="remove(row)">{{ uiText('删除') }}</el-button></template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="open" :title="uiText(id ? '编辑开关' : '新增开关')" width="720px" :loading="saving" :confirm-text="uiText('保存')" :confirm-disabled="conflict.active.value || conflict.loading.value || !guard.isCurrent()" :before-close="guard.confirmDiscard" @confirm="save">
      <p v-if="formError" role="alert">{{ formError }}</p>
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="saving || !guard.isCurrent()" :version="form.version" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <el-form label-position="top" :disabled="saving || conflict.loading.value" @submit.prevent="save">
        <el-form-item :label="uiText('开关标识')" required><el-input v-model="form.key" :disabled="!!id" :aria-label="uiText('开关标识')" maxlength="100" /><small>{{ uiText('使用小写字母开头的字母、数字、点、横线或下划线，创建后不可修改。') }}</small></el-form-item>
        <el-form-item :label="uiText('名称')" required><el-input v-model="form.name" :aria-label="uiText('名称')" maxlength="100" /></el-form-item>
        <el-form-item :label="uiText('说明')"><el-input v-model="form.description" :aria-label="uiText('说明')" type="textarea" maxlength="1000" /></el-form-item>
        <el-form-item :label="uiText('启用开关')"><el-switch v-model="form.enabled" :aria-label="uiText('启用开关')" /></el-form-item>
        <el-form-item :label="uiText('灰度比例（%）')"><el-input-number :model-value="form.rollout / 100" :min="0" :max="100" :precision="2" :step="1" :aria-label="uiText('灰度比例（%）')" @update:model-value="form.rollout = Math.round(($event ?? 0) * 100)" /><small>{{ uiText('同一用户分组保持稳定；100% 表示全部用户，排除名单优先。') }}</small></el-form-item>
        <el-form-item v-for="field in targetFields" :key="field.key" :label="uiText(field.label)">
          <el-select v-model="form[field.key]" multiple filterable remote :remote-method="(text: string) => loadTargets(field.key, text)" :loading="targetBusy[field.key]" :aria-label="uiText(field.label)" :multiple-limit="100">
            <el-option v-for="target in targets[field.key]" :key="target.id" :label="target.label" :value="target.id" />
          </el-select>
          <small>{{ uiText('每次显示最多50个搜索结果，可输入用户名或角色名称继续搜索。') }}</small>
        </el-form-item>
      </el-form>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AppLayout, BaseButton, BaseCard, BaseDialog, BaseTable } from '@/components'
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { featureFlagsApi, type FeatureFlag, type FeatureFlagWrite, type FlagTarget } from '@/api/featureFlags'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useEditConflict } from '@/composables/useEditConflict'
import { newIdempotencyKey } from '@/api'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { featureFlagMessages } from '@/i18n/featureFlagMessages'

registerUiMessages(featureFlagMessages)
const auth = useAuthStore(), modules = useModuleStore()
const rows = ref<FeatureFlag[]>([]), total = ref(0), page = ref(1), pageSize = ref(10), search = ref(''), appliedSearch = ref('')
const loading = ref(false), saving = ref(false), removing = ref(false), loadError = ref(false), open = ref(false), id = ref(''), formError = ref('')
const initial = (): FeatureFlagWrite => ({ key: '', name: '', description: '', enabled: false, rollout: 0, included_users: [], excluded_users: [], roles: [], version: 0 })
const form = reactive(initial())
const targetFields = [{ key: 'included_users', label: '指定包含用户' }, { key: 'excluded_users', label: '指定排除用户' }, { key: 'roles', label: '指定包含角色' }] as const
type TargetKey = typeof targetFields[number]['key']
const targets = reactive<Record<TargetKey, FlagTarget[]>>({ included_users: [], excluded_users: [], roles: [] })
const targetBusy = reactive<Record<TargetKey, boolean>>({ included_users: false, excluded_users: false, roles: false })
const controllers: Partial<Record<TargetKey, AbortController>> = {}
let listController: AbortController | undefined, key = '', submitted = ''
const canRead = () => auth.can('feature_flag:read') && modules.enabled('feature_flags')
const canWrite = () => canRead() && auth.can(id.value ? 'feature_flag:update' : 'feature_flag:create')
const canManage = computed(() => auth.can('feature_flag:update') || auth.can('feature_flag:delete'))
const busy = computed(() => saving.value || removing.value || loading.value || conflict.loading.value)
function clearTargets() { for (const field of targetFields) { controllers[field.key]?.abort(); targets[field.key] = []; targetBusy[field.key] = false } }
const guard = useUnsavedChanges({ source: () => form, active: () => open.value, busy: () => saving.value || conflict.loading.value,
  canEdit: canWrite, clear: () => { open.value = false; id.value = ''; Object.assign(form, initial()); formError.value = ''; clearTargets() } })
const deleteGuard = useUnsavedChanges({ source: () => null, busy: () => removing.value, canEdit: () => canRead() && auth.can('feature_flag:delete'), clear: () => {} })
function apply(row: FeatureFlag) {
  const values = Object.fromEntries(Object.keys(initial()).map(field => [field, row[field as keyof FeatureFlagWrite]]))
  id.value = row.id; Object.assign(form, JSON.parse(JSON.stringify(values))); formError.value = ''; key = newIdempotencyKey('feature-flag'); submitted = ''
  for (const field of targetFields) void loadTargets(field.key, '')
  guard.markClean()
}
const conflict = useEditConflict<FeatureFlag>({ identifier: () => open.value ? id.value : '', current: () => guard.isCurrent(), fetch: featureFlagsApi.detail, apply })
const conflictRows = computed(() => conflict.latest.value ? Object.entries(initial()).filter(([field]) => field !== 'version').map(([field]) => ({ label: uiText(({ key: '开关标识', name: '名称', description: '说明', enabled: '启用开关', rollout: '灰度比例', included_users: '指定包含用户', excluded_users: '指定排除用户', roles: '指定包含角色' } as Record<string, string>)[field] || field), local: JSON.stringify(form[field as keyof FeatureFlagWrite]), server: JSON.stringify(conflict.latest.value![field as keyof FeatureFlagWrite]) })) : [])
const columns = computed(() => [{ prop: 'key', label: uiText('开关标识'), width: 220 }, { prop: 'name', label: uiText('名称'), width: 180 },
  { prop: 'enabled', label: uiText('状态'), width: 100, render: (value: boolean) => uiText(value ? '已启用' : '已关闭') },
  { prop: 'rollout', label: uiText('灰度比例'), width: 110, render: (value: number) => `${value / 100}%` }, { prop: 'version', label: uiText('版本'), width: 80 }])
async function loadRows() {
  listController?.abort(); const controller = new AbortController(); listController = controller
  rows.value = []; total.value = 0; loadError.value = false
  if (!canRead()) return
  loading.value = true
  try { const data = await featureFlagsApi.list({ page: page.value, page_size: pageSize.value, search: appliedSearch.value }, controller.signal); if (!controller.signal.aborted && canRead()) { rows.value = data.items; total.value = data.pagination.total } }
  catch { if (!controller.signal.aborted && canRead()) loadError.value = true }
  finally { if (!controller.signal.aborted) loading.value = false }
}
function searchRows() { if (busy.value) return; appliedSearch.value = search.value.trim(); page.value = 1; void loadRows() }
function changePage(value: number) { page.value = value; void loadRows() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void loadRows() }
async function loadTargets(field: TargetKey, text: string) {
  controllers[field]?.abort(); const controller = new AbortController(); controllers[field] = controller
  if (!canRead() || !open.value) return
  targetBusy[field] = true
  try { const data = await featureFlagsApi.targets(field === 'roles' ? 'roles' : 'users', text, form[field], controller.signal); if (!controller.signal.aborted && canRead() && open.value) targets[field] = data }
  catch { if (!controller.signal.aborted && canRead() && open.value) formError.value = uiText('选项目标加载失败，请重新搜索') }
  finally { if (!controller.signal.aborted) targetBusy[field] = false }
}
function edit(row?: FeatureFlag) {
  if (busy.value || !canRead() || !auth.can(row ? 'feature_flag:update' : 'feature_flag:create')) return
  conflict.reset(); id.value = row?.id ?? ''; Object.assign(form, initial()); formError.value = ''; key = newIdempotencyKey('feature-flag'); submitted = ''; open.value = true
  if (row) apply(row)
  else for (const field of targetFields) void loadTargets(field.key, '')
}
async function save() {
  if (busy.value || conflict.active.value || !guard.isCurrent()) return
  if (!/^[a-z][a-z0-9_.-]{0,99}$/.test(form.key) || !form.name.trim() || !Number.isInteger(form.rollout) || form.rollout < 0 || form.rollout > 10000 || form.included_users.some(value => form.excluded_users.includes(value))) { formError.value = uiText('请检查开关标识、名称、灰度比例及包含排除名单'); return }
  const payload = JSON.parse(JSON.stringify(form)) as FeatureFlagWrite, digest = JSON.stringify(payload)
  if (submitted && submitted !== digest) key = newIdempotencyKey('feature-flag')
  submitted = digest; saving.value = true; formError.value = ''
  try { await featureFlagsApi.save(id.value, payload, key); if (!guard.isCurrent()) return; guard.markClean(); open.value = false; ElMessage.success(uiText('保存成功')); await loadRows() }
  catch (error: unknown) { if (!guard.isCurrent()) return; if ((error as { response?: { status: number } }).response?.status === 409 && id.value) conflict.mark(); else formError.value = uiText('保存失败，输入已保留；请检查字段或刷新选项后重试') }
  finally { saving.value = false }
}
async function remove(row: FeatureFlag) {
  if (busy.value || !deleteGuard.isCurrent()) return
  removing.value = true
  try { await ElMessageBox.confirm(uiText('确定删除此开关？使用该标识的功能将按关闭处理。'), uiText('提示'), { type: 'warning' }); if (!deleteGuard.isCurrent()) return; await featureFlagsApi.remove(row.id, row.version); if (deleteGuard.isCurrent()) { if (rows.value.length === 1 && page.value > 1) page.value--; await loadRows() } }
  catch (error: unknown) { if (error !== 'cancel' && error !== 'close' && deleteGuard.isCurrent()) ElMessage.warning(uiText('删除未确认，请刷新检查版本和状态')) }
  finally { removing.value = false }
}
watch(() => [auth.user?.id, canRead()], () => { listController?.abort(); clearTargets(); rows.value = []; total.value = 0; loading.value = false; if (canRead()) void loadRows() })
onBeforeUnmount(() => { listController?.abort(); clearTargets() })
void loadRows()
</script>

<style scoped>
.header, .filters { display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
.header { justify-content: space-between; } h2 { margin: 0; font-size: var(--font-size-lg); }
.filters { margin-bottom: var(--spacing-md); } .filters :deep(.el-input) { max-width: 340px; }
small { display: block; width: 100%; color: var(--color-text-secondary); overflow-wrap: anywhere; }
:deep(.el-select) { width: 100%; } p { overflow-wrap: anywhere; }
@media (max-width: 640px) { .filters :deep(.el-input) { max-width: 100%; flex-basis: 100%; } }
</style>
