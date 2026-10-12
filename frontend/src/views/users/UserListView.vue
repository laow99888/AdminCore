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
              <BaseButton v-if="auth.can('data_io:import')" variant="ghost" @click="triggerImport">{{ uiText("导入") }}</BaseButton>
              <BaseButton v-if="auth.can('data_io:import')" variant="ghost" @click="downloadTemplate">{{ uiText("导入模板") }}</BaseButton>
              <BaseButton v-if="auth.can('data_io:export')" variant="ghost" @click="handleExport">{{ uiText("导出") }}</BaseButton>
            </div>
          </div>
        </template>
        <el-form :model="searchForm" inline>
          <el-form-item :label="uiText('关键词')">
            <el-input
              v-model="searchForm.search"
              :placeholder="uiText('搜索用户名 / 邮箱')"
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
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <el-button v-if="auth.can('user:update')" link type="primary" size="small" @click="handleEdit(row)">{{ uiText("编辑") }}</el-button>
            <el-button v-if="auth.can('user:update')" link type="warning" size="small" @click="handleResetPassword(row)">{{ uiText("重置密码") }}</el-button>
            <el-button v-if="auth.can('user:delete')" link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
          </template>
        </BaseTable>
      </BaseCard>

      <!-- 用户编辑对话框 -->
      <BaseDialog v-model="dialogVisible" :title="dialogTitle" :loading="saving" @confirm="handleSaveUser">
        <el-form :model="formData" label-width="100px">
          <el-form-item :label="uiText('用户名')" required>
            <el-input v-model="formData.username" :disabled="!!formData.id" />
          </el-form-item>
          <el-form-item :label="uiText('邮箱')" required>
            <el-input v-model="formData.email" type="email" />
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
import { uiText } from "@/i18n/uiText"

import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { usersApi, dataIoApi, downloadFile, type UserRow } from '@/api'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const importResultVisible = ref(false)
const auth = useAuthStore()
const importError = ref('')
const importResult = ref<{ created: number; failed: number; errors?: Array<{ row: number; message: string }> } | null>(null)
const importInput = ref<HTMLInputElement>()
const tableData = ref<UserRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

const searchForm = reactive({
  search: '',
  is_active: null as boolean | null,
})

const formData = reactive({
  id: '' as string,
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  is_active: true,
  password: '',
})

const tableColumns = [
  { prop: 'username', label: uiText("用户名") },
  { prop: 'email', label: uiText("邮箱") },
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

const loadUsers = async () => {
  loading.value = true
  try {
    const data = await usersApi.list({
      ...(searchForm.search ? { search: searchForm.search } : {}),
      ...(searchForm.is_active !== null ? { is_active: searchForm.is_active } : {}),
      page: currentPage.value,
      page_size: pageSize.value,
    })
    tableData.value = data.items
    total.value = data.pagination.total
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
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
  Object.assign(formData, {
    id: '', username: '', email: '', first_name: '', last_name: '', is_active: true, password: '',
  })
  dialogVisible.value = true
}

const handleEdit = async (row: UserRow) => {
  try {
    const detail = await usersApi.detail(row.id)
    Object.assign(formData, { id: '', username: '', email: '', first_name: '', last_name: '', is_active: true, password: '' }, detail)
    dialogVisible.value = true
  } catch {
    // 请求拦截器显示错误。
  }
}

const handleSaveUser = async () => {
  if (!formData.username || !formData.email || (!formData.id && !formData.password)) {
    ElMessage.warning(uiText("请填写必填项（用户名、邮箱、初始密码）"))
    return
  }
  saving.value = true
  try {
    if (formData.id) {
      await usersApi.update(formData.id, {
        email: formData.email,
        first_name: formData.first_name,
        last_name: formData.last_name,
        is_active: formData.is_active,
      })
      ElMessage.success(uiText("修改成功"))
    } else {
      await usersApi.create({
        username: formData.username,
        email: formData.email,
        first_name: formData.first_name,
        last_name: formData.last_name,
        is_active: formData.is_active,
        password: formData.password,
      })
      ElMessage.success(uiText("创建成功"))
    }
    dialogVisible.value = false
    loadUsers()
  } catch {
    // 拦截器已提示
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

const handleResetPassword = (row: UserRow) => {
  ElMessageBox.prompt(uiText("为用户 {p0} 设置新密码（至少 8 位）", { p0: row.username }), uiText("重置密码"), {
    confirmButtonText: uiText("确定"),
    cancelButtonText: uiText("取消"),
    inputPattern: /^.{8,}$/,
    inputErrorMessage: uiText("密码至少 8 位"),
    inputType: 'password',
  })
    .then(async ({ value }) => {
      await usersApi.resetPassword(row.id, value)
      ElMessage.success(uiText("密码已重置"))
    })
    .catch(() => {})
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

const handleExport = async () => {
  await downloadFile(dataIoApi.exportUrl('users', 'xlsx'), 'users-export.xlsx')
  ElMessage.success(uiText("导出已开始下载"))
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
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.hidden-input {
  display: none;
}

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
