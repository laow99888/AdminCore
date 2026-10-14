<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="card-header-row"><h2>{{ uiText('系统参数') }}</h2><BaseButton :loading="loading" :disabled="saving" @click="reload">{{ uiText('刷新') }}</BaseButton></div></template>
      <div v-if="error" ref="errorSummary" role="alert" tabindex="-1"><el-alert :title="error" type="error" :closable="false" class="notice" /></div>
      <el-skeleton v-if="loading" :rows="5" animated />
      <el-empty v-else-if="!rows.length && !error" :description="uiText('暂无数据')" />
      <el-form v-else label-position="top" class="config-form" :disabled="saving || readingLogo">
        <el-form-item v-for="row in rows" :key="row.key" :label="uiText(row.label)">
          <div class="config-field">
            <template v-if="row.kind === 'image'">
              <img v-if="values[row.key]" :src="values[row.key]" :alt="uiText('产品 Logo')" class="logo-preview" />
              <input type="file" accept="image/png,image/jpeg,image/webp" :aria-label="uiText('选择 Logo 图片')" :disabled="saving || readingLogo || !auth.can('config:update')" @change="selectLogo($event, row.key)" />
              <el-button v-if="auth.can('config:update')" @click="values[row.key] = ''">{{ uiText('移除 Logo') }}</el-button>
            </template>
            <el-input-number v-else-if="row.kind === 'integer'" v-model="values[row.key]" :min="row.minimum" :max="row.maximum" :disabled="!auth.can('config:update')" />
            <el-input v-else v-model="values[row.key]" :maxlength="row.maximum" show-word-limit :disabled="!auth.can('config:update')" />
            <BaseButton v-if="auth.can('config:update')" variant="primary" :loading="savingKey === row.key" @click="save(row)">{{ uiText('保存') }}</BaseButton>
          </div>
          <div class="help">{{ row.key }} · {{ uiText(row.effective) }}</div>
        </el-form-item>
      </el-form>
    </BaseCard>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { AppLayout, BaseCard, BaseButton } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useBrandStore } from '@/stores/brand'
import { systemApi, type ConfigRow } from '@/api/system'
import { uiText } from '@/i18n/uiText'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'

const auth = useAuthStore()
const brand = useBrandStore()
const rows = ref<ConfigRow[]>([])
const values = reactive<Record<string, any>>({})
const loading = ref(false)
const savingKey = ref('')
const saving = computed(() => !!savingKey.value)
const error = ref('')
const readingLogo = ref(false)
const formGuard = useUnsavedChanges({ source: () => rows.value.filter(row => JSON.stringify(values[row.key]) !== JSON.stringify(row.value)).map(row => ({ key: row.key, value: values[row.key] })), active: () => !!rows.value.length, busy: () => saving.value || loading.value || readingLogo.value, canEdit: () => auth.can('config:update'), clear: () => { for (const key of Object.keys(values)) delete values[key] } })
useErrorSummary(error)
async function selectLogo(event: Event, key: string) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || saving.value || readingLogo.value || !auth.can('config:update')) return
  if (file.size > 200 * 1024 || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    error.value = uiText('请选择不超过 200 KB 的 PNG、JPEG 或 WebP 图片'); input.value = ''; return
  }
  const owner = auth.user?.id
  readingLogo.value = true
  try {
    const value = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file)
    })
    if (auth.can('config:update') && auth.isAuthenticated && auth.user?.id === owner) { values[key] = value; error.value = '' }
  } catch { error.value = uiText('图片读取失败，请重试') }
  finally { readingLogo.value = false }
}
async function reload() { if (saving.value || loading.value || readingLogo.value || !await formGuard.confirmDiscard()) return; await load() }
async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await systemApi.configs()
    rows.value.forEach(row => { values[row.key] = row.value })
    formGuard.markClean()
  } catch { error.value = uiText('参数加载失败，请重试') }
  finally { loading.value = false }
}
async function save(row: ConfigRow) {
  if (saving.value || loading.value || readingLogo.value || !auth.can('config:update')) return
  const value = values[row.key]
  if ((row.kind === 'integer' && (!Number.isInteger(value) || value < row.minimum || value > row.maximum)) ||
      (row.kind === 'string' && (typeof value !== 'string' || value.trim().length < row.minimum || value.trim().length > row.maximum))) {
    error.value = uiText('参数值不符合允许范围')
    return
  }
  const owner = auth.user?.id
  savingKey.value = row.key
  error.value = ''
  try {
    const response = await systemApi.configUpdate(row, value)
    if (auth.user?.id !== owner || !auth.can('config:update')) return
    const updated = response.data.data[0] as ConfigRow
    Object.assign(row, updated)
    values[row.key] = updated.value

    ElMessage.success(uiText('保存成功'))
    if (row.key.startsWith('brand.')) await brand.load()
  } catch (exception: any) {
    error.value = uiText(exception?.response?.status === 409 ? '内容已被其他人修改，已保留输入，请刷新后重试' : '保存失败，已保留输入')
  } finally { savingKey.value = '' }
}
onMounted(load)
</script>

<style scoped>
h2 { font-size: var(--font-size-lg); margin: 0; }
.notice { margin-bottom: var(--spacing-lg); }
.config-form { max-width: 760px; }
.config-field { display: flex; align-items: center; gap: var(--spacing-md); width: 100%; }
.help { font-size: var(--font-size-sm); color: var(--color-text-secondary); overflow-wrap: anywhere; }
.logo-preview { width: 48px; height: 48px; object-fit: contain; }
.config-field input[type="file"] { max-width: 100%; }
@media (max-width: 600px) { .config-field { flex-wrap: wrap; } }
</style>
