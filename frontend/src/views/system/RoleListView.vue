<template>
  <AppLayout>
    <div class="role-list-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("角色列表") }}</div>
            <BaseButton v-if="auth.can('role:update') && (auth.user?.is_staff || auth.user?.is_superuser)" variant="primary" @click="handleCreate">{{ uiText("+ 新增角色") }}</BaseButton>
          </div>
        </template>

        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :show-index="true"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <el-button link type="primary" size="small" @click="handleViewPermissions(row)">{{ uiText("查看权限") }}</el-button>
            <el-button v-if="auth.can('role:update') && (auth.user?.is_staff || auth.user?.is_superuser)" link type="primary" size="small" @click="handleEdit(row)">{{ uiText("编辑") }}</el-button>
            <el-button v-if="auth.can('role:update') && (auth.user?.is_staff || auth.user?.is_superuser)" link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
          </template>
        </BaseTable>
      </BaseCard>

      <!-- 角色编辑 -->
      <BaseDialog v-model="dialogVisible" :title="formData.id ? uiText('编辑角色') : uiText('新增角色')" :loading="saving" @confirm="handleSave">
        <el-form :model="formData" label-width="90px">
          <el-form-item :label="uiText('角色名')" required>
            <el-input v-model="formData.name" />
          </el-form-item>
          <el-form-item :label="uiText('描述')">
            <el-input v-model="formData.description" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item :label="uiText('激活')">
            <el-switch v-model="formData.is_active" />
          </el-form-item>
          <el-form-item :label="uiText('权限')">
            <el-select
              v-model="formData.permission_ids"
              multiple
              filterable
              clearable
              :placeholder="uiText('选择该角色的权限')"
              style="width: 100%"
            >
              <el-option
                v-for="perm in allPermissions"
                :key="perm.id"
                :label="`${perm.name}（${perm.code}）`"
                :value="perm.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </BaseDialog>

      <!-- 权限查看 -->
      <BaseDialog v-model="permDialogVisible" :title="uiText('角色权限 — {p0}', { p0: currentRole?.name || '' })" :show-cancel="false" :confirm-text="uiText('关闭')" @confirm="permDialogVisible = false">
        <div v-if="currentRole?.permissions?.length" class="perm-list">
          <el-tag v-for="perm in currentRole.permissions" :key="perm.id" class="perm-tag" type="success">
            {{ perm.name }}（{{ perm.code }}）
          </el-tag>
        </div>
        <el-empty v-else :description="uiText('该角色暂未分配权限')" :image-size="80" />
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { rolesApi, permissionsApi, type RoleRow } from '@/api'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const permDialogVisible = ref(false)
const currentRole = ref<RoleRow | null>(null)
const allPermissions = ref<Array<{ id: string; name: string; code: string }>>([])
const tableData = ref<RoleRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

const formData = reactive({
  id: '',
  name: '',
  description: '',
  is_active: true,
  permission_ids: [] as string[],
})

const tableColumns = [
  { prop: 'name', label: uiText("角色名") },
  { prop: 'description', label: uiText("描述") },
  {
    prop: 'permissions',
    label: uiText("权限数"),
    width: '100px',
    render: (_v: any, row: RoleRow) => String(row.permissions?.length || 0),
  },
  {
    prop: 'is_active',
    label: uiText("状态"),
    width: '90px',
    render: (value: boolean) => (value ? uiText("激活") : uiText("停用")),
  },
  { prop: 'created_at', label: uiText("创建时间"), width: '180px' },
]

const loadRoles = async () => {
  loading.value = true
  try {
    const data = await rolesApi.list({ page: currentPage.value, page_size: pageSize.value })
    tableData.value = data.items
    total.value = data.pagination.total
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  Object.assign(formData, { id: '', name: '', description: '', is_active: true, permission_ids: [] })
  dialogVisible.value = true
}

const handleEdit = (row: RoleRow) => {
  Object.assign(formData, {
    id: row.id,
    name: row.name,
    description: row.description,
    is_active: row.is_active,
    permission_ids: (row.permissions || []).map((p) => p.id),
  })
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!formData.name) {
    ElMessage.warning(uiText("请填写角色名"))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: formData.name,
      description: formData.description,
      is_active: formData.is_active,
      permission_ids: formData.permission_ids,
    }
    if (formData.id) {
      await rolesApi.update(formData.id, payload)
      ElMessage.success(uiText("修改成功"))
    } else {
      await rolesApi.create(payload)
      ElMessage.success(uiText("创建成功"))
    }
    dialogVisible.value = false
    loadRoles()
  } finally {
    saving.value = false
  }
}

const handleDelete = (row: RoleRow) => {
  ElMessageBox.confirm(uiText("确定删除角色 {p0} 吗？", { p0: row.name }), uiText("提示"), { type: 'warning' })
    .then(async () => {
      await rolesApi.remove(row.id)
      ElMessage.success(uiText("删除成功"))
      loadRoles()
    })
    .catch(() => {})
}

const handleViewPermissions = (row: RoleRow) => {
  currentRole.value = row
  permDialogVisible.value = true
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadRoles()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadRoles()
}

const loadPermissions = async () => {
  try {
    const permissions = []
    let page = 1
    while (true) {
      const data = await permissionsApi.list({ page, page_size: 100 })
      permissions.push(...data.items)
      if (page >= data.pagination.total_pages) break
      page += 1
    }
    allPermissions.value = permissions
  } catch {
    // 拦截器已提示
  }
}

onMounted(loadPermissions)
loadRoles()
</script>

<style scoped>
.role-list-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.perm-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.perm-tag {
  border-radius: var(--radius-md);
}
</style>
