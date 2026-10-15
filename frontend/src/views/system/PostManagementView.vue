<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="header"><h2>{{ uiText('岗位与任职') }}</h2><DataImportButton v-if="section === 'posts'" resource="posts" :loading="loading || formBusy" /><BaseButton variant="primary" :disabled="loading || formBusy" @click="edit()">{{ uiText(section === 'posts' ? '新增岗位' : '分配岗位') }}</BaseButton></div></template>
      <el-alert :title="uiText('岗位描述任职，不授予角色权限；停用保留历史任职，删除前需移除任职。')" type="info" :closable="false" />
      <el-tabs v-model="section" @tab-change="changeSection"><el-tab-pane :label="uiText('岗位')" name="posts" /><el-tab-pane :label="uiText('人员任职')" name="user-posts" /></el-tabs>
      <div class="search"><el-input v-model="search" :aria-label="uiText('搜索岗位或用户名')" :placeholder="uiText('搜索岗位或用户名')" maxlength="100" clearable @keyup.enter="searchRows" /><BaseButton :disabled="loading" @click="searchRows">{{ uiText('搜索') }}</BaseButton><BaseButton :disabled="loading" @click="loadRows">{{ uiText('刷新') }}</BaseButton></div>
      <el-alert v-if="error" :title="uiText('列表加载失败，请刷新重试')" type="error" :closable="false" />
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :action-width="130" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }"><el-button v-if="section === 'posts'" link type="primary" :disabled="formBusy" @click="edit(row)">{{ uiText('编辑') }}</el-button><el-button link type="danger" :disabled="formBusy" @click="remove(row)">{{ uiText(section === 'posts' ? '删除' : '移除任职') }}</el-button></template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="visible" :before-close="formGuard.confirmDiscard" :title="uiText(section === 'posts' ? (form.id ? '编辑岗位' : '新增岗位') : '分配岗位')" :loading="formBusy" :confirm-disabled="conflict.active.value || choicesLoading || !!choicesError" @confirm="save">
      <div v-if="formError" ref="errorSummary" tabindex="-1"><el-alert :title="formError" type="error" :closable="false" /></div>
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="saving || !formGuard.isCurrent()" :version="form.version" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <el-form label-position="top" :disabled="formBusy">
        <template v-if="section === 'posts'">
          <el-form-item :label="uiText('岗位编码')" required><el-input v-model="form.code" :disabled="!!form.id" maxlength="64" :aria-label="uiText('岗位编码')" /><small>{{ uiText('小写字母开头，仅含小写字母、数字和下划线，创建后不可修改') }}</small></el-form-item>
          <el-form-item :label="uiText('岗位名称')" required><el-input v-model="form.name" maxlength="100" :aria-label="uiText('岗位名称')" /></el-form-item>
          <el-form-item :label="uiText('岗位说明')"><el-input v-model="form.description" type="textarea" maxlength="500" :aria-label="uiText('岗位说明')" /></el-form-item>
          <el-form-item :label="uiText('排序')"><el-input-number v-model="form.order" :min="0" :max="2147483647" /></el-form-item>
          <el-form-item :label="uiText('启用')"><el-switch v-model="form.is_active" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item :label="uiText('人员')" required><PersonPicker v-model="person" purpose="post" :disabled="saving || !visible" /></el-form-item>
          <p v-if="choicesLoading" role="status">{{ uiText('正在加载岗位') }}</p>
          <div v-else-if="choicesError" role="alert"><p>{{ uiText('岗位加载失败，请重试') }}</p><el-button @click="loadChoices">{{ uiText('重试') }}</el-button></div>
          <p v-else-if="!choices.length" role="status">{{ uiText('没有启用岗位，请先新增岗位') }}</p>
          <el-form-item :label="uiText('岗位')" required><el-select v-model="postId" :disabled="choicesLoading || !!choicesError" filterable :aria-label="uiText('岗位')" style="width: 100%"><el-option v-for="post in choices" :key="post.id" :label="`${post.name} (${post.code})`" :value="post.id" /></el-select></el-form-item>
        </template>
      </el-form>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { usePageState } from '@/composables/usePageState'
import { useEditConflict } from '@/composables/useEditConflict'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AppLayout, BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import PersonPicker from '@/components/common/PersonPicker.vue'
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { postsApi, type PostRow, type UserPostRow, type PostSection } from '@/api/posts'
import type { Person } from '@/api/personnel'
import { uiText } from '@/i18n/uiText'
import DataImportButton from '@/components/common/DataImportButton.vue'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
const auth = useAuthStore(), modules = useModuleStore()
const section = ref<PostSection>('posts'), rows = ref<Array<PostRow | UserPostRow>>([]), page = ref(1), pageSize = ref(10), total = ref(0), search = ref(''), appliedSearch = ref('')
usePageState({ section, page, pageSize, search, appliedSearch })
const loading = ref(false), saving = ref(false), error = ref(false), formError = ref(''), dialogOpen = ref(false)
const formBusy = computed(() => saving.value || conflict.loading.value)
const visible = computed({ get: () => dialogOpen.value, set: value => { if (!formBusy.value) dialogOpen.value = value } })
const form = reactive<PostRow>({ id: '', code: '', name: '', description: '', order: 0, is_active: true, version: 0 })
const person = ref<Person | null>(null), postId = ref(''), choices = ref<PostRow[]>([]), choicesLoading = ref(false), choicesError = ref(false)
const canRead = () => auth.can('post:read') && !!(auth.user?.is_staff || auth.user?.is_superuser) && modules.pathEnabled('/organization/posts')
const formGuard = useUnsavedChanges({ source: () => ({ form, person: person.value, postId: postId.value }), active: () => visible.value, busy: () => formBusy.value, canEdit: () => canRead() && auth.can('post:update'), clear: () => { dialogOpen.value = false; person.value = null; postId.value = ''; formError.value = ''; Object.assign(form, { id: '', code: '', name: '', description: '', order: 0, is_active: true, version: 0 }) } })
const conflict = useEditConflict<PostRow>({ identifier: () => visible.value && section.value === 'posts' ? form.id : '', current: () => formGuard.isCurrent(), fetch: postsApi.detail,
  apply: row => { Object.assign(form, row); formError.value = ''; formGuard.markClean() } })
const conflictRows = computed(() => {
  const server = conflict.latest.value
  if (!server) return []
  return ([['code', '岗位编码'], ['name', '岗位名称'], ['description', '岗位说明'], ['order', '排序'], ['is_active', '启用']] as const)
    .map(([key, label]) => ({ label: uiText(label), local: key === 'is_active' ? uiText(form[key] ? '启用' : '停用') : String(form[key]), server: key === 'is_active' ? uiText(server[key] ? '启用' : '停用') : String(server[key]) }))
})
useErrorSummary(formError)
const columns = computed(() => section.value === 'posts' ? [
  { prop: 'code', label: uiText('岗位编码'), width: 160 }, { prop: 'name', label: uiText('岗位名称'), width: 180 },
  { prop: 'description', label: uiText('岗位说明') }, { prop: 'is_active', label: uiText('状态'), width: 90, render: (value: boolean) => uiText(value ? '启用' : '停用') },
] : [{ prop: 'username', label: uiText('用户名'), width: 160 }, { prop: 'post_name', label: uiText('岗位名称'), width: 180 },
  { prop: 'post_active', label: uiText('岗位状态'), width: 110, render: (value: boolean) => uiText(value ? '启用' : '停用') },
  { prop: 'user_active', label: uiText('账号状态'), width: 110, render: (value: boolean) => uiText(value ? '启用' : '停用') }])
let generation = 0, alive = true
async function loadRows() {
  const current = ++generation; loading.value = true; error.value = false; rows.value = []; total.value = 0
  if (!canRead()) { loading.value = false; return }
  try { const data = await postsApi.list<PostRow | UserPostRow>(section.value, { page: page.value, page_size: pageSize.value, search: appliedSearch.value }); if (alive && current === generation && canRead()) { rows.value = data.items; total.value = data.pagination.total } }
  catch { if (alive && current === generation) error.value = true }
  finally { if (alive && current === generation) loading.value = false }
}
function changeSection() { conflict.reset(); formGuard.discard(); page.value = 1; search.value = ''; appliedSearch.value = ''; void loadRows() }
function searchRows() { page.value = 1; appliedSearch.value = search.value.trim(); void loadRows() }
function changePage(value: number) { page.value = value; void loadRows() }
function changeSize(value: number) { pageSize.value = value; page.value = 1; void loadRows() }
async function loadChoices() { choicesLoading.value = true; choicesError.value = false; choices.value = []; try { choices.value = await postsApi.choices() } catch { choicesError.value = true } finally { choicesLoading.value = false } }
function edit(row?: PostRow) {
  if (!formGuard.isCurrent() || formBusy.value) return
  formError.value = ''; conflict.reset(); person.value = null; postId.value = ''
  Object.assign(form, row || { id: '', code: '', name: '', description: '', order: 0, is_active: true, version: 0 })
  dialogOpen.value = true
  if (section.value === 'user-posts') void loadChoices()
}
async function save() {
  if (formBusy.value || conflict.active.value || choicesLoading.value || choicesError.value || !formGuard.isCurrent()) return
  formError.value = ''
  if (section.value === 'posts' && (!/^[a-z][a-z0-9_]{0,63}$/.test(form.code) || !form.name.trim())) { formError.value = uiText('请填写有效岗位编码和名称'); return }
  if (section.value === 'user-posts' && (!person.value || !postId.value)) { formError.value = uiText('请选择人员和岗位'); return }
  saving.value = true
  try {
    if (section.value === 'posts') { const { id, ...data } = form; await postsApi.save(id, { ...data, name: data.name.trim() }) }
    else await postsApi.assign(person.value!.id, postId.value)
    if (!formGuard.isCurrent()) return
    dialogOpen.value = false; ElMessage.success(uiText('保存成功')); await loadRows()
  } catch (err: any) { if (!formGuard.isCurrent()) return; if (err.response?.status === 409 && form.id && section.value === 'posts') conflict.mark(); else formError.value = uiText('保存失败，输入已保留；请检查字段或刷新选项后重试') }
  finally { saving.value = false }
}
async function remove(row: PostRow | UserPostRow) {
  if (formBusy.value || !formGuard.isCurrent()) return
  try { await ElMessageBox.confirm(uiText('确定移除此记录？'), uiText('提示'), { type: 'warning' }) } catch { return }
  if (formBusy.value || !formGuard.isCurrent()) return
  saving.value = true
  try { await postsApi.remove(section.value, row.id, row.version); if (rows.value.length === 1 && page.value > 1) page.value--; await loadRows() }
  catch { ElMessage.warning(uiText('移除失败，请刷新后检查版本或关联任职')) }
  finally { saving.value = false }
}
watch(() => [auth.user?.id, canRead()], () => { generation++; rows.value = []; total.value = 0; if (canRead()) void loadRows() })
onBeforeUnmount(() => { alive = false; generation++ })
void loadRows()
</script>

<style scoped>
.header, .search { display: flex; align-items: center; gap: var(--spacing-sm); }
.header { justify-content: space-between; flex-wrap: wrap; }
.header h2 { margin: 0; font-size: var(--font-size-lg); }
.search { margin: var(--spacing-md) 0; }
.search :deep(.el-input) { max-width: 360px; }
small { color: var(--color-text-secondary); overflow-wrap: anywhere; }
@media (max-width: 640px) { .search { flex-wrap: wrap; } .search :deep(.el-input) { flex-basis: 100%; } }
</style>
