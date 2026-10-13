<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="card-header-row"><h2>{{ uiText('数据字典') }}</h2><BaseButton v-if="auth.can('dictionary:update')" variant="primary" @click="edit()">{{ uiText('新增字典') }}</BaseButton></div></template>
      <el-form inline @submit.prevent="search">
        <el-form-item :label="uiText('关键词')"><el-input v-model="keyword" clearable /></el-form-item>
        <el-form-item><BaseButton :loading="loading" @click="search">{{ uiText('搜索') }}</BaseButton></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" class="notice" />
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" @update:currentPage="changePage" @update:pageSize="changeSize">
        <template #actions="{ row }"><el-button v-if="auth.can('dictionary:update')" link type="primary" @click="edit(row)">{{ uiText('编辑') }}</el-button></template>
      </BaseTable>
    </BaseCard>
    <BaseDialog v-model="visible" :title="uiText(form.id ? '编辑字典' : '新增字典')" :loading="saving" @confirm="save">
      <div v-if="formError" ref="errorSummary" role="alert" tabindex="-1"><el-alert :title="formError" type="error" :closable="false" class="notice" /></div>
      <el-form label-position="top" :disabled="saving">
        <el-form-item :label="uiText('编码')" required><el-input v-model="form.code" :disabled="!!form.id" maxlength="64" /></el-form-item>
        <el-form-item :label="uiText('名称')" required><el-input v-model="form.name" maxlength="100" /></el-form-item>
        <el-form-item :label="uiText('描述')"><el-input v-model="form.description" maxlength="500" /></el-form-item>
        <el-form-item :label="uiText('启用')"><el-switch v-model="form.is_active" /></el-form-item>
        <fieldset v-for="(item, index) in form.items" :key="index" class="dict-item">
          <legend>{{ uiText('字典项') }} {{ index + 1 }}</legend>
          <el-form-item :label="uiText('名称')" required><el-input v-model="item.label" maxlength="100" /></el-form-item>
          <el-form-item :label="uiText('值')" required><el-input v-model="item.value" maxlength="100" /></el-form-item>
          <div class="item-actions">
            <el-form-item :label="uiText('排序')"><el-input-number v-model="item.order" :min="0" :max="100000" /></el-form-item>
            <el-form-item :label="uiText('启用')"><el-switch v-model="item.is_active" /></el-form-item>
            <el-button type="danger" plain @click="form.items.splice(index, 1)">{{ uiText('移除字典项') }}</el-button>
          </div>
        </fieldset>
        <el-button :disabled="form.items.length >= 500" @click="addItem">{{ uiText('添加字典项') }}</el-button>
      </el-form>
    </BaseDialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { AppLayout, BaseCard, BaseButton, BaseTable, BaseDialog } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { systemApi, type DictionaryRow } from '@/api/system'
import { uiText } from '@/i18n/uiText'
import { useErrorSummary } from '@/composables/useErrorSummary'

const auth = useAuthStore()
const rows = ref<DictionaryRow[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const keyword = ref('')
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const error = ref('')
const formError = ref('')
useErrorSummary(formError)
const form = reactive<DictionaryRow>({ id: '', code: '', name: '', description: '', is_active: true, items: [], version: 0 })
const columns = computed(() => [{ prop: 'code', label: uiText('编码'), width: 180 }, { prop: 'name', label: uiText('名称'), width: 200 },
  { prop: 'is_active', label: uiText('状态'), width: 100, render: (value: boolean) => uiText(value ? '启用' : '停用') }])
async function load() {
  loading.value = true
  error.value = ''
  try { const data = await systemApi.dictionaries(page.value, keyword.value, pageSize.value); rows.value = data.items; total.value = data.pagination.total }
  catch { error.value = uiText('字典加载失败，请重试') }
  finally { loading.value = false }
}
function changePage(value: number) { page.value = value; load() }
function changeSize(value: number) { pageSize.value = value; page.value = 1; load() }
function search() { page.value = 1; load() }
function edit(row?: DictionaryRow) {
  Object.assign(form, row ? JSON.parse(JSON.stringify(row)) : { id: '', code: '', name: '', description: '', is_active: true, items: [], version: 0 })
  formError.value = ''
  visible.value = true
}
function addItem() { form.items.push({ label: '', value: '', order: form.items.length, is_active: true }) }
async function save() {
  if (saving.value) return
  formError.value = ''
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(form.code) || !form.name.trim()) { formError.value = uiText('请填写有效编码和名称'); return }
  if (form.items.some(item => !item.label.trim() || !item.value) || new Set(form.items.map(item => item.value)).size !== form.items.length) {
    formError.value = uiText('字典项名称和值必填，值不能重复'); return
  }
  saving.value = true
  formError.value = ''
  try {
    const { id, ...data } = form
    if (id) await systemApi.updateDictionary(id, data)
    else await systemApi.createDictionary(data)
    visible.value = false
    ElMessage.success(uiText('保存成功'))
    await load()
  } catch (exception: any) {
    formError.value = uiText(exception?.response?.status === 409 ? '内容已被其他人修改，已保留输入，请重新打开编辑窗口' : '保存失败，已保留输入')
  } finally { saving.value = false }
}
onMounted(load)
</script>

<style scoped>
h2 { font-size: var(--font-size-lg); margin: 0; }
.notice { margin-bottom: var(--spacing-lg); }
.dict-item { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--spacing-md); margin: 0 0 var(--spacing-md); min-width: 0; }
legend { color: var(--color-text-secondary); }
.item-actions { display: flex; align-items: center; gap: var(--spacing-md); flex-wrap: wrap; }
</style>
