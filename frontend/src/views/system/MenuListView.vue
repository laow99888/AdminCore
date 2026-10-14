<template>
  <AppLayout>
    <BaseCard>
      <template #header>
        <div class="card-header-row">
          <div class="card-header-title">{{ uiText('菜单结构') }}</div>
          <div class="menu-actions">
            <BaseButton variant="ghost" :disabled="loading" @click="loadMenus">{{ uiText('刷新') }}</BaseButton>
            <BaseButton v-if="auth.can('menu:update')" variant="primary" @click="openEditor()">{{ uiText('新增菜单') }}</BaseButton>
          </div>
        </div>
      </template>
      <el-alert v-if="loadFailed" :title="uiText('菜单加载失败，请点击刷新重试')" type="error" :closable="false" />
      <el-table v-loading="loading" :data="menuTree" row-key="id" default-expand-all style="width: 100%">
        <el-table-column prop="name" :label="uiText('菜单名')" min-width="150" />
        <el-table-column prop="path" :label="uiText('路由路径')" min-width="150" />
        <el-table-column :label="uiText('图标')" width="70">
          <template #default="{ row }"><component :is="menuIcons[row.icon]" v-if="menuIcons[row.icon]" :size="16" aria-hidden="true" /><span v-else>—</span></template>
        </el-table-column>
        <el-table-column prop="order" :label="uiText('排序')" width="70" />
        <el-table-column :label="uiText('可见')" width="80">
          <template #default="{ row }"><el-tag :type="row.is_visible ? 'success' : 'info'" size="small">{{ row.is_visible ? uiText('可见') : uiText('隐藏') }}</el-tag></template>
        </el-table-column>
        <el-table-column v-if="auth.can('menu:update')" :label="uiText('操作')" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditor(row)">{{ uiText('编辑') }}</el-button>
            <el-button link type="danger" :disabled="!!row.children?.length" @click="removeMenu(row)">{{ uiText('删除') }}</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty :description="uiText('暂无菜单数据')" :image-size="80" /></template>
      </el-table>
    </BaseCard>
    <BaseDialog v-model="dialogVisible" :before-close="formGuard.confirmDiscard" :title="form.id ? uiText('编辑菜单') : uiText('新增菜单')" width="560px" :loading="saving || permissionsLoading" :confirm-disabled="permissionsFailed" @confirm="saveMenu">
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px" :disabled="saving">
        <el-form-item :label="uiText('菜单名')" prop="name"><el-input v-model="form.name" maxlength="100" /></el-form-item>
        <el-form-item :label="uiText('路由路径')" prop="path"><el-input v-model="form.path" placeholder="/users" maxlength="200" /></el-form-item>
        <el-form-item :label="uiText('父菜单')"><el-select v-model="form.parent" clearable style="width: 100%"><el-option v-for="menu in parentOptions" :key="menu.id" :label="menu.name" :value="menu.id" /></el-select></el-form-item>
        <el-form-item :label="uiText('所需权限')"><el-select v-model="form.permission" clearable filterable :loading="permissionsLoading" :disabled="permissionsLoading || permissionsFailed" style="width: 100%"><el-option v-for="permission in permissionOptions" :key="permission.id" :label="permission.name" :value="permission.id" /></el-select></el-form-item>
        <el-form-item :label="uiText('图标')"><el-select v-model="form.icon" clearable style="width: 100%"><el-option v-for="(_icon, name) in menuIcons" :key="name" :label="String(name)" :value="name" /></el-select></el-form-item>
        <el-form-item :label="uiText('排序')"><el-input-number v-model="form.order" :min="0" :precision="0" /></el-form-item>
        <el-form-item :label="uiText('可见')"><el-switch v-model="form.is_visible" /></el-form-item>
      </el-form>
      <p class="menu-help">{{ uiText('菜单指向已有页面；新增菜单不会自动创建业务页面。父菜单有子项时不能直接删除。') }}</p>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { isAxiosError } from 'axios'
import { uiText } from '@/i18n/uiText'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseDialog } from '@/components'
import { menuIcons } from '@/components/layout/menuIcons'
import { menusApi, permissionsApi, type MenuRow } from '@/api'

const auth = useAuthStore()
const menuTree = ref<MenuRow[]>([])
const loading = ref(false)
const loadFailed = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const formError = ref('')
const permissionsLoading = ref(false)
const permissionsFailed = ref(false)
const permissionOptions = ref<Array<{ id: string; name: string }>>([])
const emptyForm = () => ({ id: '', name: '', path: '', icon: '', order: 0, parent: null as string | null, permission: null as string | null, is_visible: true })
const form = reactive(emptyForm())
const formGuard = useUnsavedChanges({ source: () => form, active: () => dialogVisible.value, busy: () => saving.value, canEdit: () => auth.can('menu:update'), clear: () => { dialogVisible.value = false; Object.assign(form, emptyForm()) } })
const rules: FormRules = {
  name: [{ required: true, message: uiText('请输入菜单名'), trigger: 'blur' }],
  path: [{ required: true, pattern: /^\/(?!\/)[^?#\\]*$/, message: uiText('请输入以 / 开头的站内路由'), trigger: 'blur' }],
}
const flatten = (rows: MenuRow[]): MenuRow[] => rows.flatMap((row) => [row, ...flatten(row.children || [])])
const parentOptions = computed(() => {
  const current = flatten(menuTree.value).find((row) => row.id === form.id)
  const excluded = new Set(current ? flatten([current]).map((row) => row.id) : [])
  return flatten(menuTree.value).filter((row) => !excluded.has(row.id))
})
const loadMenus = async () => {
  loading.value = true
  loadFailed.value = false
  try { menuTree.value = await menusApi.list() } catch { loadFailed.value = true } finally { loading.value = false }
}
const loadPermissions = async () => {
  permissionsLoading.value = true
  permissionsFailed.value = false
  try {
    const items: Array<{ id: string; name: string }> = []
    let page = 1
    let totalPages = 1
    do {
      const data = await permissionsApi.list({ page, page_size: 100 })
      items.push(...data.items)
      totalPages = data.pagination.total_pages
      page += 1
    } while (page <= totalPages)
    permissionOptions.value = items
  } catch {
    permissionsFailed.value = true
    formError.value = uiText('权限加载失败，请重新打开编辑窗口')
  } finally { permissionsLoading.value = false }
}
const openEditor = (row?: MenuRow) => {
  Object.assign(form, row ? { id: row.id, name: row.name, path: row.path, icon: row.icon, order: row.order, parent: row.parent || null, permission: row.permission || null, is_visible: row.is_visible } : emptyForm())
  formError.value = ''
  dialogVisible.value = true
  loadPermissions()
}
const saveMenu = async () => {
  if (saving.value || permissionsLoading.value || permissionsFailed.value || !auth.can('menu:update')) return
  saving.value = true
  formError.value = ''
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    if (!formGuard.isCurrent()) return
    const { id, ...data } = form
    data.parent ||= null
    data.permission ||= null
    if (id) await menusApi.update(id, data)
    else await menusApi.create(data)
    ElMessage.success(uiText('保存成功'))
    dialogVisible.value = false
    await loadMenus()
    window.dispatchEvent(new Event('admincore:menus-updated'))
  } catch (error) {
    formError.value = isAxiosError(error) && error.response?.data?.data
      ? Object.values(error.response.data.data).flat().join('；') : uiText('保存失败，请重试')
  } finally { saving.value = false }
}
const removeMenu = async (row: MenuRow) => {
  try {
    await ElMessageBox.confirm(uiText('确定删除菜单 {p0} 吗？', { p0: row.name }), uiText('提示'), { type: 'warning' })
    await menusApi.remove(row.id)
    await loadMenus()
    window.dispatchEvent(new Event('admincore:menus-updated'))
    ElMessage.success(uiText('删除成功'))
  } catch { /* 取消不提示；接口错误由拦截器提示。 */ }
}
loadMenus()
</script>

<style scoped>
.card-header-row, .menu-actions { display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
.card-header-row { justify-content: space-between; }
.card-header-title { font-weight: var(--font-weight-semibold); }
.menu-help { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
</style>
