<template>
  <AppLayout>
    <div class="user-list-container">
      <!-- 搜索和操作栏 -->
      <BaseCard class="search-card">
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("用户查询") }}</div>
            <div class="header-actions">
              <input ref="importInput" type="file" accept=".xlsx,.csv" class="hidden-input" @change="handleImport" />
              <BaseButton v-if="modules.enabled('data_io') && auth.can('data_io:import') && auth.can('user:create')" variant="ghost" @click="triggerImport">{{ uiText("导入") }}</BaseButton>
              <BaseButton v-if="modules.enabled('data_io') && auth.can('data_io:import') && auth.can('user:create')" variant="ghost" @click="downloadTemplate">{{ uiText("导入模板") }}</BaseButton>
              <DataExportButton :loading="loading || !exportReady" resource="users" :filters="exportFilters" />
              <LocalExportButton resource="users" :title="uiText('用户列表')" :rows="tableData" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :owner-key="printOwner" />
              <PrintTableButton :title="uiText('用户列表')" :rows="tableData" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :allowed="auth.can('user:read')" :owner-key="printOwner" />
            </div>
          </div>
        </template>
        <el-form :model="searchForm" inline>
          <el-form-item :label="uiText('关键词')">
            <el-input
              v-model="searchForm.search"
              :placeholder="uiText('搜索用户名 / 姓名')"
              clearable
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item :label="uiText('状态')">
            <el-select v-model="searchForm.is_active" clearable :placeholder="uiText('全部')" style="width: 120px">
              <el-option :label="uiText('激活')" :value="true" />
              <el-option :label="uiText('禁用')" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <BaseButton variant="primary" @click="handleSearch">{{ uiText("搜索") }}</BaseButton>
            <BaseButton variant="ghost" @click="handleReset">{{ uiText("重置") }}</BaseButton>
          </el-form-item>
        </el-form>
      </BaseCard>

      <!-- 用户列表 -->
      <BaseCard class="list-card" style="margin-top: var(--spacing-lg)">
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("用户列表") }}</div>
            <BaseButton v-if="auth.can('user:create')" variant="primary" @click="handleCreate">{{ uiText("+ 新增用户") }}</BaseButton>
          </div>
        </template>

        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          action-width="300"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <el-button v-if="auth.can('user:read') && auth.can('user:sensitive_read')" link type="primary" size="small" @click="sensitiveTarget = { id: row.id, username: row.username }">{{ uiText('查看原值') }}</el-button>
            <el-button v-if="auth.can('user:update')" link type="primary" size="small" @click="handleEdit(row)">{{ uiText("编辑") }}</el-button>
            <el-button v-if="auth.can('user:update')" link type="warning" size="small" @click="handleResetPassword(row)">{{ uiText("重置密码") }}</el-button>
            <el-button v-if="auth.can('user:delete')" link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
          </template>
        </BaseTable>
      </BaseCard>

      <!-- 用户编辑对话框 -->
      <BaseDialog v-model="dialogVisible" :before-close="formGuard.confirmDiscard" :title="dialogTitle" :loading="saving || rolesLoading || conflict.loading.value" :confirm-disabled="rolesFailed || conflict.active.value" @confirm="handleSaveUser">
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
        <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="saving || !formGuard.isCurrent()" :version="formData.version" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
        <el-form :model="formData" label-width="100px" :disabled="saving">
          <el-form-item :label="uiText('用户名')" required>
            <el-input v-model="formData.username" :disabled="!!formData.id" />
          </el-form-item>
          <el-alert v-if="formData.id" :title="uiText('邮箱和电话已脱敏；留空保持原值，填写新值会替换原值。')" type="info" :closable="false" />
          <el-form-item :label="uiText('邮箱')" :required="!formData.id">
            <div class="contact-field">
              <p v-if="formData.id">{{ uiText('当前脱敏值：{p0}', { p0: maskedContact.email || uiText('未填写') }) }}</p>
              <el-input v-model="formData.email" type="email" :placeholder="formData.id ? uiText('留空保持原邮箱') : ''" />
            </div>
          </el-form-item>
          <el-form-item :label="uiText('电话')">
            <div class="contact-field">
              <p v-if="formData.id">{{ uiText('当前脱敏值：{p0}', { p0: maskedContact.phone || uiText('未填写') }) }}</p>
              <el-input v-model="formData.phone" type="tel" maxlength="20" :disabled="saving || formData.clear_phone" :placeholder="formData.id ? uiText('留空保持原电话') : ''" />
              <el-checkbox v-if="formData.id" v-model="formData.clear_phone" @change="formData.phone = ''">{{ uiText('清空已保存电话') }}</el-checkbox>
            </div>
          </el-form-item>
          <el-form-item :label="uiText('名字')">
            <el-input v-model="formData.first_name" />
          </el-form-item>
          <el-form-item :label="uiText('姓氏')">
            <el-input v-model="formData.last_name" />
          </el-form-item>
          <el-form-item :label="uiText('状态')">
            <el-switch v-model="formData.is_active" />
          </el-form-item>
          <el-form-item v-if="!formData.id" :label="uiText('密码')" required>
            <el-input v-model="formData.password" type="password" show-password :placeholder="uiText('初始密码')" />
          </el-form-item>
          <el-form-item v-if="!formData.id" :label="uiText('下次登录必须修改密码')">
            <el-switch v-model="formData.must_change_password" :aria-label="uiText('下次登录必须修改密码')" />
          </el-form-item>
          <el-form-item v-if="auth.user?.is_staff || auth.user?.is_superuser" :label="uiText('角色')">
            <el-select v-model="formData.role_ids" multiple :loading="rolesLoading" :disabled="rolesLoading || rolesFailed" :placeholder="uiText('选择用户角色')" style="width: 100%">
              <el-option v-for="role in roleOptions" :key="role.id" :label="role.name" :value="role.id" :disabled="!role.is_active && !formData.role_ids.includes(role.id)" />
            </el-select>
            <el-alert v-if="rolesFailed" :title="uiText('角色加载失败，请重新打开编辑窗口')" type="error" :closable="false" />
          </el-form-item>
        </el-form>
      </BaseDialog>

      <UserSensitiveDialog v-if="sensitiveTarget" :target="sensitiveTarget" @close="sensitiveTarget = undefined" />

      <BaseDialog v-model="resetVisible" :before-close="resetGuard.confirmDiscard" :title="uiText('重置密码')" :loading="resetSaving" @confirm="saveResetPassword">
        <el-form label-position="top" :disabled="resetSaving">
          <p>{{ resetTarget?.username }}</p>
          <el-form-item :label="uiText('新密码')" required>
            <el-input v-model="resetValue" type="password" show-password autocomplete="new-password" :disabled="resetSaving" />
          </el-form-item>
          <el-form-item :label="uiText('下次登录必须修改密码')">
            <el-switch v-model="resetRequired" :aria-label="uiText('下次登录必须修改密码')" :disabled="resetSaving" />
          </el-form-item>
        </el-form>
      </BaseDialog>

      <!-- 导入结果对话框 -->
      <BaseDialog v-model="importResultVisible" :title="uiText('导入结果')" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="importResultVisible = false">
        <el-alert v-if="importError" type="error" :title="importError" :closable="false" show-icon />
        <div v-if="importResult">
          <el-result
            :icon="importResult.failed ? 'warning' : 'success'"
            :title="uiText('成功 {p0} 条，失败 {p1} 条', { p0: importResult.created, p1: importResult.failed })"
          />
          <div v-if="importResult.errors?.length" class="import-errors">
            <div v-for="(err, i) in importResult.errors" :key="i" class="error-line">{{ uiText("第") }}{{ err.row }}{{ uiText("行：") }}{{ err.message }}
            </div>
          </div>
        </div>
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { useEditConflict } from '@/composables/useEditConflict'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { usersApi, rolesApi, dataIoApi, downloadFile, type UserRow, type UserDetail, type RoleRow } from '@/api'
import DataExportButton from '@/components/common/DataExportButton.vue'
import PrintTableButton from '@/components/common/PrintTableButton.vue'
import LocalExportButton from '@/components/common/LocalExportButton.vue'
import UserSensitiveDialog from '@/components/auth/UserSensitiveDialog.vue'
import { userContactPatch } from '@/utils/userContactPatch'
import type { PrintColumn } from '@/utils/printDocument'

const loading = ref(false)
const saving = ref(false)
const formError = ref('')
const dialogVisible = ref(false)
const importResultVisible = ref(false)
const auth = useAuthStore()
const sensitiveTarget = ref<{ id: string; username: string }>()
const maskedContact = reactive({ email: '', phone: '' })
const modules = useModuleStore()
const roleOptions = ref<RoleRow[]>([])
const rolesLoading = ref(false)
const rolesFailed = ref(false)
const loadRoleOptions = async () => {
  if (!(auth.user?.is_staff || auth.user?.is_superuser)) return
  rolesLoading.value = true
  rolesFailed.value = false
  try {
    const rows: RoleRow[] = []
    let page = 1
    let totalPages = 1
    do {
      const data = await rolesApi.list({ page, page_size: 100 })
      rows.push(...data.items)
      totalPages = data.pagination.total_pages
      page += 1
    } while (page <= totalPages)
    roleOptions.value = rows
  } catch {
    rolesFailed.value = true
  } finally {
    rolesLoading.value = false
  }
}
const importError = ref('')
const importResult = ref<{ created: number; failed: number; errors?: Array<{ row: number; message: string }> } | null>(null)
const importInput = ref<HTMLInputElement>()
const tableData = ref<UserRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const exportFilters = ref<{ search?: string; is_active?: boolean }>({})
const printOwner = computed(() => JSON.stringify([auth.user?.id, auth.token, auth.user?.permissions, modules.config]))
const printColumns = computed<PrintColumn<UserRow>[]>(() => [
  { label: uiText('用户名'), value: row => row.username },
  { label: uiText('邮箱'), value: row => row.email },
  { label: uiText('电话'), value: row => row.phone },
  { label: uiText('名字'), value: row => row.first_name },
  { label: uiText('姓氏'), value: row => row.last_name },
  { label: uiText('状态'), value: row => uiText(row.is_active ? '激活' : '禁用') },
])

const searchForm = reactive({
  search: '',
  is_active: null as boolean | null,
})

usePageState({ searchForm, currentPage, pageSize })
const formData = reactive({
  id: '' as string,
  version: 0,
  username: '',
  email: '',
  phone: '',
  clear_phone: false,
  first_name: '',
  last_name: '',
  is_active: true,
  password: '',
  must_change_password: true,
  role_ids: [] as string[],
})

const formGuard = useUnsavedChanges({ source: () => formData, active: () => dialogVisible.value, busy: () => saving.value || conflict.loading.value, canEdit: () => auth.can(formData.id ? 'user:update' : 'user:create'), clear: () => { dialogVisible.value = false; Object.assign(maskedContact, { email: '', phone: '' }); Object.assign(formData, { id: '', version: 0, username: '', email: '', phone: '', clear_phone: false, first_name: '', last_name: '', is_active: true, password: '', role_ids: [], must_change_password: true }) } })
function applyUser(detail: UserDetail) {
  Object.assign(maskedContact, { email: detail.email, phone: detail.phone || '' })
  Object.assign(formData, { id: detail.id, version: detail.version, username: detail.username, email: '', phone: '', clear_phone: false, first_name: detail.first_name, last_name: detail.last_name, is_active: detail.is_active, password: '', role_ids: detail.roles.map(role => role.role__id) })
  formError.value = ''; formGuard.markClean()
}
const conflict = useEditConflict<UserDetail>({ identifier: () => dialogVisible.value ? formData.id : '', current: () => formGuard.isCurrent(), fetch: usersApi.detail, apply: applyUser })
const conflictRows = computed(() => {
  const server = conflict.latest.value
  if (!server) return []
  return [
    { label: uiText('名字'), local: formData.first_name, server: server.first_name },
    { label: uiText('姓氏'), local: formData.last_name, server: server.last_name },
    { label: uiText('邮箱'), local: formData.email || maskedContact.email, server: server.email },
    { label: uiText('电话'), local: formData.clear_phone ? '' : formData.phone || maskedContact.phone, server: server.phone || '' },
    { label: uiText('状态'), local: String(formData.is_active), server: String(server.is_active) },
    { label: uiText('角色'), local: formData.role_ids.join(', '), server: server.roles.map(role => role.role__id).join(', ') },
  ]
})
const tableColumns = [
  { prop: 'username', label: uiText("用户名") },
  { prop: 'email', label: uiText("邮箱") },
  { prop: 'phone', label: uiText("电话") },
  { prop: 'first_name', label: uiText("名字") },
  { prop: 'last_name', label: uiText("姓氏") },
  { prop: 'login_count', label: uiText("登录次数"), width: '100px' },
  {
    prop: 'is_active',
    label: uiText("状态"),
    width: '90px',
    render: (value: boolean) => (value ? uiText("激活") : uiText("禁用")),
  },
  { prop: 'created_at', label: uiText("创建时间"), width: '180px' },
]

const dialogTitle = computed(() => (formData.id ? uiText("编辑用户") : uiText("新增用户")))

let listGeneration = 0
const exportReady = ref(false)
const loadUsers = async () => {
  const current = ++listGeneration
  exportReady.value = false
  loading.value = true
  const filters = { ...(searchForm.search ? { search: searchForm.search } : {}),
    ...(typeof searchForm.is_active === 'boolean' ? { is_active: searchForm.is_active } : {}) }
  try {
    const data = await usersApi.list({
      ...filters,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    if (current !== listGeneration) return
    tableData.value = data.items
    exportFilters.value = filters
    exportReady.value = true
    total.value = data.pagination.total
  } catch {
    // 拦截器已提示
  } finally {
    if (current === listGeneration) loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  loadUsers()
}

const handleReset = () => {
  searchForm.search = ''
  searchForm.is_active = null
  currentPage.value = 1
  loadUsers()
}

const handleCreate = () => {
  conflict.reset(); formError.value = ''
  Object.assign(formData, {
    id: '', version: 0, username: '', email: '', phone: '', clear_phone: false, first_name: '', last_name: '', is_active: true, password: '', role_ids: [], must_change_password: true,
  })
  dialogVisible.value = true
  loadRoleOptions()
}

const handleEdit = async (row: UserRow) => {
  if (saving.value || dialogVisible.value || !auth.can('user:update')) return
  const owner = auth.user?.id
  try {
    const detail = await usersApi.detail(row.id)
    if (auth.user?.id !== owner || !auth.can('user:update') || !formGuard.isSessionCurrent()) return
    conflict.reset(); applyUser(detail)
    dialogVisible.value = true
    loadRoleOptions()
  } catch {
    // 请求拦截器显示错误。
  }
}

const handleSaveUser = async () => {
  if (saving.value || conflict.active.value || rolesLoading.value || rolesFailed.value || !auth.can(formData.id ? 'user:update' : 'user:create')) return
  if (!formData.username || (!formData.id && (!formData.email.trim() || !formData.password))) {
    ElMessage.warning(uiText("请填写必填项（用户名、邮箱、初始密码）"))
    return
  }
  let contacts: { email?: string; phone?: string }
  try { contacts = userContactPatch(formData.email, formData.phone, formData.clear_phone) }
  catch { ElMessage.warning(uiText('请输入完整的新邮箱或电话，不能提交脱敏值。')); return }
  saving.value = true
  try {
    if (formData.id) {
      await usersApi.update(formData.id, {
        version: formData.version,
        ...contacts,
        first_name: formData.first_name,
        last_name: formData.last_name,
        is_active: formData.is_active,
        ...((auth.user?.is_staff || auth.user?.is_superuser) ? { role_ids: formData.role_ids } : {}),
      })
      if (!formGuard.isCurrent()) return
      ElMessage.success(uiText("修改成功"))
    } else {
      await usersApi.create({
        username: formData.username,
        ...contacts,
        first_name: formData.first_name,
        last_name: formData.last_name,
        is_active: formData.is_active,
        password: formData.password,
        must_change_password: formData.must_change_password,
        ...((auth.user?.is_staff || auth.user?.is_superuser) ? { role_ids: formData.role_ids } : {}),
      })
      if (!formGuard.isCurrent()) return
      ElMessage.success(uiText("创建成功"))
    }
    dialogVisible.value = false
    loadUsers()
  } catch (error: any) {
    if (formGuard.isCurrent()) {
      if (error.response?.status === 409 && formData.id) conflict.mark()
      else formError.value = uiText('保存失败，已保留输入')
    }
  } finally {
    saving.value = false
  }
}

const handleDelete = (row: UserRow) => {
  ElMessageBox.confirm(uiText("确定删除用户 {p0} 吗？", { p0: row.username }), uiText("提示"), {
    confirmButtonText: uiText("确定"),
    cancelButtonText: uiText("取消"),
    type: 'warning',
  })
    .then(async () => {
      await usersApi.remove(row.id)
      ElMessage.success(uiText("删除成功"))
      loadUsers()
    })
    .catch(() => {})
}

const resetVisible = ref(false)
const resetSaving = ref(false)
const resetTarget = ref<UserRow>()
const resetValue = ref('')
const resetRequired = ref(true)
const resetGuard = useUnsavedChanges({ source: () => ({ value: resetValue.value, required: resetRequired.value }), active: () => resetVisible.value, busy: () => resetSaving.value, canEdit: () => auth.can('user:update'), clear: () => { resetVisible.value = false; resetValue.value = ''; resetRequired.value = true; resetTarget.value = undefined } })
const handleResetPassword = (row: UserRow) => {
  resetTarget.value = row
  resetValue.value = ''
  resetRequired.value = true
  resetVisible.value = true
}
const saveResetPassword = async () => {
  if (resetSaving.value || !resetTarget.value || !auth.can('user:update')) return
  if (resetValue.value.length < 8) { ElMessage.warning(uiText('密码至少 8 位')); return }
  resetSaving.value = true
  try {
    await usersApi.resetPassword(resetTarget.value.id, resetValue.value, resetRequired.value)
    resetValue.value = ''
    resetVisible.value = false
    ElMessage.success(uiText('密码已重置'))
  } catch { /* 拦截器已提示，保留表单供修改。 */ }
  finally { resetSaving.value = false }
}

// ===== 导入导出 =====
const triggerImport = () => importInput.value?.click()

const handleImport = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一文件
  if (!file) return

  const res = await dataIoApi.importUsers(file)
  const task = res.data?.data
  importError.value = task?.status === 'failed' ? (task.error || uiText("导入失败")) : ''
  if (task?.status === 'success' || task?.status === 'failed') {
    importResult.value = task.status === 'failed' ? null : task.result
    importResultVisible.value = true
  } else {
    ElMessage.success(uiText("导入任务已提交，请稍后在任务中心查看结果"))
  }
  loadUsers()
}

const downloadTemplate = () => {
  downloadFile(dataIoApi.templateUrl(), 'import-template-users.xlsx')
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadUsers()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadUsers()
}

// 初始加载
loadUsers()
</script>

<style scoped>
.user-list-container {
  width: 100%;
}

.search-card {
  margin-bottom: var(--spacing-lg);
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
  flex-shrink: 0;
}

.hidden-input {
  display: none;
}

.contact-field { min-width: 0; width: 100%; }
.contact-field p { color: var(--color-text-secondary); overflow-wrap: anywhere; margin-top: 0; }
.contact-field :deep(.el-input) { width: 100%; }

:deep(.el-form-item) {
  margin-bottom: var(--spacing-lg);
}

:deep(.el-input),
:deep(.el-select) {
  width: 200px;
}

.import-errors {
  max-height: 240px;
  overflow-y: auto;
  padding: var(--spacing-md);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
}

.error-line {
  font-size: var(--font-size-sm);
  color: var(--color-error);
  line-height: 1.8;
}
</style>
