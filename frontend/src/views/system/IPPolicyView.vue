<template>
  <AppLayout><BaseCard>
    <template #header><div class="header"><h2>{{ uiText('IP 访问策略') }}</h2><BaseButton :disabled="busy" @click="refresh">{{ uiText('刷新') }}</BaseButton></div></template>
    <p>{{ uiText('策略作用于 API、后台和实时连接；请先预检当前来源，再输入当前密码保存。') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">{{ uiText('加载中...') }}</p>
    <template v-if="loaded">
      <p v-if="!canWrite">{{ uiText('仅具备读取权限，不能修改策略。') }}</p>
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :disabled="busy || !guard.isCurrent()" :version="form.version" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item :label="uiText('启用 IP 策略')"><el-switch v-model="form.enabled" :disabled="!canWrite || busy" :aria-label="uiText('启用 IP 策略')" /></el-form-item>
        <p>{{ uiText('每行一个 IPv4、IPv6 或 CIDR，最多 100 条；拒绝规则优先，允许列表为空表示不限制。') }}</p>
        <el-form-item v-for="field in networkFields" :key="field.key" :label="uiText(field.label)"><el-input v-model="form[field.key]" type="textarea" :rows="5" :maxlength="8200" :disabled="!canWrite || busy" :aria-label="uiText(field.label)" spellcheck="false" /></el-form-item>
        <div class="actions"><BaseButton :disabled="busy" @click="preview">{{ uiText('预检当前来源') }}</BaseButton><span v-if="result" role="status">{{ uiText('当前来源：{p0}；结果：{p1}', { p0: result.source_ip || uiText('来源未知'), p1: uiText(result.allowed ? '允许访问' : '拒绝访问') }) }}</span></div>
        <template v-if="canWrite">
          <el-form-item :label="uiText('当前密码')" required><el-input v-model="password" type="password" autocomplete="current-password" :maxlength="4096" :disabled="busy" :aria-label="uiText('当前密码')" /></el-form-item>
          <BaseButton :disabled="busy || conflict.active.value || !result?.allowed || !password || !guard.isCurrent()" @click="save">{{ uiText('保存') }}</BaseButton>
        </template>
      </el-form>
    </template>
  </BaseCard></AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { AppLayout, BaseButton, BaseCard } from '@/components'
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { ipPolicyApi, type IPPolicy, type IPPolicyConfig, type IPPolicyPreview } from '@/api/ipPolicy'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useEditConflict } from '@/composables/useEditConflict'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { ipPolicyMessages } from '@/i18n/ipPolicyMessages'
registerUiMessages(ipPolicyMessages)
const auth = useAuthStore(), modules = useModuleStore()
const canRead = computed(() => modules.enabled('ip_policy') && auth.can('ip_policy:read'))
const canWrite = computed(() => canRead.value && auth.can('ip_policy:update'))
const initial = () => ({ enabled: false, allow: '', deny: '', version: 1 })
const form = reactive(initial()), password = ref(''), error = ref(''), loaded = ref(false)
const loading = ref(false), saving = ref(false), previewing = ref(false), result = ref<IPPolicyPreview>()
const networkFields = [{ key: 'allow', label: '允许网络' }, { key: 'deny', label: '拒绝网络' }] as const
let readController: AbortController | undefined, previewController: AbortController | undefined
const guard = useUnsavedChanges({ source: () => form, active: () => loaded.value && canWrite.value,
  busy: () => saving.value || previewing.value || conflict.loading.value, canEdit: () => canRead.value,
  clear: () => { password.value = ''; Object.assign(form, initial()); loaded.value = false; result.value = undefined; error.value = ''; previewController?.abort() } })
function apply(value: IPPolicy) {
  Object.assign(form, { enabled: value.enabled, allow: value.allow.join('\n'), deny: value.deny.join('\n'), version: value.version })
  password.value = ''; result.value = undefined; error.value = ''; loaded.value = true; guard.markClean()
}
const conflict = useEditConflict<IPPolicy>({ identifier: () => loaded.value ? '1' : '', current: () => guard.isCurrent() && canWrite.value, fetch: ipPolicyApi.detail, apply })
const conflictRows = computed(() => conflict.latest.value ? [
  { label: uiText('启用 IP 策略'), local: String(form.enabled), server: String(conflict.latest.value.enabled) },
  ...networkFields.map(field => ({ label: uiText(field.label), local: form[field.key], server: conflict.latest.value![field.key].join('\n') })),
] : [])
const busy = computed(() => loading.value || saving.value || previewing.value || conflict.loading.value)
function configuration(): IPPolicyConfig {
  const lines = (value: string) => value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  const allow = lines(form.allow), deny = lines(form.deny)
  if ([allow, deny].some(values => values.length > 100 || values.some(value => value.length > 80))) throw new Error(uiText('网络条目最多 100 条，每条最多 80 个字符'))
  return { enabled: form.enabled, allow, deny }
}
async function load() {
  readController?.abort(); const controller = new AbortController(); readController = controller
  if (!canRead.value || !guard.isSessionCurrent()) return
  loading.value = true; error.value = ''; loaded.value = false
  try { const data = await ipPolicyApi.detail('1', controller.signal); if (!controller.signal.aborted && canRead.value && guard.isSessionCurrent()) apply(data) }
  catch { if (!controller.signal.aborted && canRead.value) error.value = uiText('加载失败，请重试') }
  finally { if (!controller.signal.aborted) loading.value = false }
}
async function refresh() { if (busy.value || !await guard.confirmDiscard()) return; conflict.reset(); password.value = ''; await load() }
async function preview() {
  if (busy.value || !canRead.value || !guard.isSessionCurrent() || !loaded.value) return
  let config: IPPolicyConfig
  try { config = configuration() } catch (failure) { error.value = (failure as Error).message; return }
  previewController?.abort(); const controller = new AbortController(); previewController = controller
  previewing.value = true; result.value = undefined; error.value = ''
  try { const data = await ipPolicyApi.preview(config, controller.signal); if (!controller.signal.aborted && guard.isCurrent()) result.value = data }
  catch { if (!controller.signal.aborted && guard.isCurrent()) error.value = uiText('策略预检失败，请检查网络格式或重试') }
  finally { if (!controller.signal.aborted) previewing.value = false }
}
async function save() {
  if (busy.value || !canWrite.value || !guard.isCurrent() || conflict.active.value) return
  if (!result.value?.allowed) { error.value = uiText('请先预检并确认当前来源允许访问'); return }
  if (!password.value) { error.value = uiText('请输入当前密码确认修改'); return }
  const payload = { ...configuration(), version: form.version, current_password: password.value }
  password.value = ''; saving.value = true; error.value = ''
  try { const data = await ipPolicyApi.save(payload); if (guard.isCurrent() && canWrite.value) { apply(data); ElMessage.success(uiText('保存成功')) } }
  catch (failure: unknown) { if (guard.isCurrent() && canWrite.value) { if ((failure as { response?: { status: number } }).response?.status === 409) conflict.mark(); else error.value = uiText('保存失败，请检查字段和密码后重试') } }
  finally { saving.value = false }
}
watch(() => [form.enabled, form.allow, form.deny], () => { result.value = undefined; previewController?.abort(); previewing.value = false }, { flush: 'sync' })
watch(() => [auth.user?.id, canRead.value, canWrite.value], () => {
  readController?.abort(); previewController?.abort(); conflict.reset(); guard.discard(); loading.value = false; previewing.value = false
  if (canRead.value && guard.isSessionCurrent()) void load()
}, { flush: 'sync' })
onBeforeUnmount(() => { readController?.abort(); previewController?.abort(); password.value = '' })
void load()
</script>

<style scoped>
.header, .actions { display: flex; gap: var(--spacing-sm); align-items: center; flex-wrap: wrap; }
.header { justify-content: space-between; } h2 { margin: 0; font-size: var(--font-size-lg); }
.actions { margin-bottom: var(--spacing-md); } p, span { overflow-wrap: anywhere; }
:deep(.el-form) { max-width: 800px; } :deep(.el-textarea__inner) { overflow-wrap: anywhere; }
</style>
