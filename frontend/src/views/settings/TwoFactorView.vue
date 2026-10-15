<template>
  <AppLayout>
    <div class="two-factor-page">
      <div class="page-heading"><div><h1>{{ uiText('双因素认证') }}</h1><p>{{ uiText('使用标准 TOTP 认证器；动态码失效时可使用一次性恢复码。') }}</p></div><BaseButton size="large" variant="ghost" :disabled="busy || !!setup || recoveryCodes.length > 0" :loading="loading" @click="load">{{ uiText('刷新') }}</BaseButton></div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon role="status" />
      <p v-if="loading" role="status">{{ uiText('正在加载双因素认证状态') }}</p>
      <BaseCard v-if="status">
        <p>{{ uiText('认证状态') }}: <strong>{{ uiText(status.enabled ? '已启用' : '未启用') }}</strong></p>
        <p v-if="status.enabled">{{ uiText('剩余恢复码：{p0}', { p0: status.recovery_codes_remaining }) }}</p>
        <el-alert v-if="!status.available" :title="uiText('双因素认证暂不可用，请联系管理员完成安全配置。')" type="info" :closable="false" show-icon />
        <template v-if="recoveryCodes.length">
          <h2>{{ uiText('保存一次性恢复码') }}</h2>
          <p class="hint">{{ uiText('恢复码仅在此展示一次，每条只能使用一次。请离线妥善保存，不要与密码保存在一起。') }}</p>
          <ul class="recovery-codes"><li v-for="item in recoveryCodes" :key="item"><code>{{ item }}</code></li></ul>
          <BaseButton size="large" variant="ghost" @click="copy(recoveryCodes.join('\n'))">{{ uiText('复制恢复码') }}</BaseButton>
          <el-checkbox v-model="codesSaved">{{ uiText('我已保存恢复码') }}</el-checkbox>
          <BaseButton size="large" type="primary" variant="primary" :disabled="!codesSaved" @click="closeCodes">{{ uiText('完成并清除恢复码') }}</BaseButton>
        </template>
        <template v-else-if="status.available">
          <template v-if="setup">
            <h2>{{ uiText('在认证器中添加账号') }}</h2>
            <p class="hint">{{ uiText('选择手动输入密钥，使用基于时间的 6 位动态码；或将以下 URI 导入支持的本地认证器。') }}</p>
            <dl><dt>{{ uiText('手动密钥') }}</dt><dd><code>{{ setup.secret }}</code></dd><dt>{{ uiText('认证器 URI') }}</dt><dd><code>{{ setup.otpauth_uri }}</code></dd></dl>
            <div class="actions"><BaseButton size="large" variant="ghost" :disabled="busy || expired" @click="copy(setup.secret)">{{ uiText('复制密钥') }}</BaseButton><BaseButton size="large" variant="ghost" :disabled="busy || expired" @click="copy(setup.otpauth_uri)">{{ uiText('复制认证器 URI') }}</BaseButton></div>
            <p role="status">{{ expired ? uiText('设置已过期，请取消后重新生成密钥。') : uiText('设置有效期剩余 {p0} 秒', { p0: seconds }) }}</p>
          </template>
          <el-form label-position="top" :disabled="busy" @submit.prevent="setup ? enable() : startSetup()">
            <el-form-item :label="uiText('当前密码')"><el-input v-model="password" :aria-label="uiText('当前密码')" type="password" show-password autocomplete="current-password" maxlength="1024" /></el-form-item>
            <el-form-item v-if="setup || status.enabled" :label="uiText(setup ? '认证器动态码' : '动态码或恢复码')"><el-input v-model="otpCode" :aria-label="uiText(setup ? '认证器动态码' : '动态码或恢复码')" autocomplete="one-time-code" maxlength="64" /></el-form-item>
            <div class="actions">
              <BaseButton v-if="!status.enabled && !setup" size="large" variant="primary" type="primary" native-type="submit" :disabled="busy || !password" :loading="busy">{{ uiText('生成认证器密钥') }}</BaseButton>
              <BaseButton v-if="setup" size="large" variant="primary" type="primary" native-type="submit" :disabled="busy || expired || !password || !otpCode.trim()" :loading="busy">{{ uiText('确认启用双因素认证') }}</BaseButton>
              <template v-if="status.enabled"><BaseButton size="large" variant="ghost" :disabled="busy || !password || !otpCode.trim()" @click="modify('regenerate')">{{ uiText('重新生成恢复码') }}</BaseButton><BaseButton size="large" variant="danger" :disabled="busy || !password || !otpCode.trim()" @click="modify('disable')">{{ uiText('停用双因素认证') }}</BaseButton></template>
              <BaseButton size="large" variant="ghost" :disabled="busy" @click="cancel">{{ uiText('取消') }}</BaseButton>
            </div>
          </el-form>
          <p class="hint">{{ uiText('启用、停用或重新生成恢复码会撤销全部旧会话；当前会话会安全替换，请重新登录其他设备。') }}</p>
        </template>
      </BaseCard>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseCard } from '@/components'
import { totpApi, type TotpSetup, type TotpStatus, type TotpSession } from '@/api/totp'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { useAuthStore } from '@/stores/auth'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { twoFactorMessages } from '@/i18n/twoFactorMessages'
registerUiMessages(twoFactorMessages)

const auth = useAuthStore()
const router = useRouter()
const status = ref<TotpStatus>(), setup = ref<TotpSetup>(), password = ref(''), otpCode = ref(''), recoveryCodes = ref<string[]>([]), codesSaved = ref(false)
const loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), now = ref(Date.now())
const seconds = computed(() => Math.max(0, Math.ceil((Date.parse(setup.value?.expires_at ?? '') - now.value) / 1000)))
const expired = computed(() => !Number.isFinite(seconds.value) || seconds.value <= 0)
let alive = true, controller: AbortController | undefined
const timer = window.setInterval(() => { now.value = Date.now(); if (setup.value && expired.value) { setup.value.secret = ''; setup.value.otpauth_uri = ''; password.value = ''; otpCode.value = '' } }, 1000)
function clearInputs() { password.value = ''; otpCode.value = '' }
function clearSecrets() { clearInputs(); setup.value = undefined; recoveryCodes.value = []; codesSaved.value = false }
const current = (token: string | null) => alive && tokensBelongToSameSession(token, localStorage.getItem('token'))
async function load() {
  if (busy.value) return
  controller?.abort(); controller = new AbortController(); const active = controller, token = localStorage.getItem('token')
  loading.value = true; error.value = ''; status.value = undefined
  try { const value = await totpApi.status(active.signal); if (current(token) && !active.signal.aborted) status.value = value }
  catch { if (current(token) && !active.signal.aborted) error.value = uiText('双因素认证状态加载失败，请刷新重试。') }
  finally { if (alive && !active.signal.aborted) loading.value = false }
}
async function startSetup() {
  if (busy.value || !status.value?.available || status.value.enabled || !password.value) return
  const token = localStorage.getItem('token'), supplied = password.value
  clearInputs(); busy.value = true; error.value = ''; notice.value = ''
  try { const value = await totpApi.setup(supplied); if (current(token)) { setup.value = value; now.value = Date.now() } }
  catch { if (current(token)) error.value = uiText('密钥生成未确认，请重新输入密码后重试。') }
  finally { if (alive) busy.value = false }
}
function applySession(value: TotpSession, token: string | null, enabled: boolean) {
  if (!current(token) || !auth.replaceSecuritySession(value, token)) return
  clearSecrets(); recoveryCodes.value = value.recovery_codes?.slice() ?? []
  status.value = { available: true, enabled, recovery_codes_remaining: enabled ? recoveryCodes.value.length : 0 }
  notice.value = uiText(enabled ? '双因素认证已更新；全部旧会话已撤销，请保存恢复码。' : '双因素认证已停用；全部旧会话已撤销。')
}
async function enable() {
  if (busy.value || !setup.value || expired.value || !password.value || !otpCode.value.trim()) return
  if (!/^\d{6}$/.test(otpCode.value.trim())) { error.value = uiText('首次启用请填写认证器的 6 位动态码'); return }
  const token = localStorage.getItem('token'), supplied = password.value, code = otpCode.value.trim()
  clearInputs(); busy.value = true; error.value = ''; notice.value = ''
  try { const value = await totpApi.enable(supplied, code); applySession(value, token, true) }
  catch { if (current(token)) error.value = uiText('启用未确认，请检查密码和认证器动态码后重试。') }
  finally { if (alive) busy.value = false }
}
async function modify(action: 'disable' | 'regenerate') {
  if (busy.value || !status.value?.enabled || !password.value || !otpCode.value.trim()) return
  busy.value = true
  try { await ElMessageBox.confirm(uiText(action === 'disable' ? '确定停用双因素认证并撤销旧会话吗？' : '重新生成将使所有旧恢复码失效并撤销旧会话，继续吗？'), uiText('提示'), { confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), closeOnClickModal: false, type: 'warning' }) }
  catch { clearInputs(); if (alive) busy.value = false; return }
  if (!alive || !password.value || !otpCode.value.trim()) { busy.value = false; return }
  const token = localStorage.getItem('token'), supplied = password.value, code = otpCode.value.trim()
  clearInputs(); busy.value = true; error.value = ''; notice.value = ''
  try { const value = await totpApi[action](supplied, code); applySession(value, token, action !== 'disable') }
  catch { if (current(token)) error.value = uiText('安全修改未确认，请重新输入密码和动态码或恢复码后重试。') }
  finally { if (alive) busy.value = false }
}
async function copy(value: string) {
  if (!value) return
  try { await navigator.clipboard.writeText(value); if (alive) notice.value = uiText('已复制，请妥善保存并及时清理剪贴板。') }
  catch { if (alive) error.value = uiText('复制失败，请手动选中并保存。') }
}
function closeCodes() { if (codesSaved.value) { recoveryCodes.value = []; codesSaved.value = false; notice.value = uiText('恢复码已从页面清除。') } }
function cancel() { if (!busy.value) { clearSecrets(); error.value = ''; notice.value = '' } }
function sessionCleared() { clearSecrets() }
async function storageChanged(event: StorageEvent) {
  if (event.key !== 'token' || tokensBelongToSameSession(event.oldValue, event.newValue)) return
  clearSecrets(); status.value = undefined; controller?.abort()
  if (!event.newValue) { void router.replace('/login'); return }
  await auth.fetchUser(true)
  if (alive && tokensBelongToSameSession(event.newValue, localStorage.getItem('token'))) void load()
}
function beforeUnload(event: BeforeUnloadEvent) { if (busy.value || setup.value || password.value || otpCode.value || (recoveryCodes.value.length && !codesSaved.value)) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(async to => {
  if (['/login', '/403', '/unavailable', '/change-password'].includes(to.path) || !localStorage.getItem('token')) { clearSecrets(); return true }
  if (busy.value) return false
  if ((recoveryCodes.value.length && !codesSaved.value) || setup.value) {
    try { await ElMessageBox.confirm(uiText('离开后密钥和未保存的恢复码将清除，确定离开吗？'), uiText('提示'), { confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), closeOnClickModal: false, type: 'warning' }) }
    catch { return false }
  }
  clearSecrets(); return true
})
window.addEventListener('admincore:session-cleared', sessionCleared)
window.addEventListener('beforeunload', beforeUnload)
window.addEventListener('storage', storageChanged)
void load()
onBeforeUnmount(() => { alive = false; controller?.abort(); window.clearInterval(timer); window.removeEventListener('admincore:session-cleared', sessionCleared); window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('storage', storageChanged); clearSecrets() })
</script>

<style scoped>
.two-factor-page { display: grid; gap: var(--spacing-lg); min-width: 0; }
.page-heading { display: flex; justify-content: space-between; gap: var(--spacing-md); align-items: flex-start; }
.page-heading > div { min-width: 0; }
h1 { margin: 0 0 var(--spacing-sm); font-size: var(--font-size-xl); }
h2 { font-size: var(--font-size-lg); margin-top: var(--spacing-lg); }
p, dd, code { overflow-wrap: anywhere; line-height: 1.6; }
.hint, .page-heading p, dt { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
dd { margin: var(--spacing-sm) 0 var(--spacing-md); }
.actions { display: flex; gap: var(--spacing-sm); flex-wrap: wrap; }
.recovery-codes { padding-left: var(--spacing-lg); display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-sm); }
:deep(.el-checkbox) { display: block; margin: var(--spacing-md) 0; height: auto; white-space: normal; }
:deep(.el-checkbox__label) { white-space: normal; }
@media (max-width: 768px) { .page-heading { flex-wrap: wrap; } .recovery-codes { grid-template-columns: 1fr; } }
</style>
