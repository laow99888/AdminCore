<template>
  <main class="enterprise-login">
    <section class="login-panel" :aria-label="uiText('企业身份登录')">
      <h1>{{ uiText('企业身份登录') }}</h1>
      <p>{{ uiText('企业身份仅用于验证已绑定的本地账号，权限由本系统管理。') }}</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <p v-if="loading" role="status">{{ uiText('正在检查企业登录配置') }}</p>
      <template v-else-if="enabled">
        <p v-if="ready" role="status">{{ uiText('企业身份已验证，请完成本地安全校验。') }}</p>
        <el-form v-if="ready" label-position="top" @submit.prevent="finish">
          <el-form-item v-if="mfaRequired" :label="uiText('动态码或恢复码')"><el-input v-model="otpCode" :aria-label="uiText('动态码或恢复码')" autocomplete="one-time-code" maxlength="32" :disabled="busy" /></el-form-item>
          <section v-if="captcha.required" class="captcha-panel">
            <img :src="captcha.image" :alt="uiText('图形验证码')" width="180" height="64" />
            <el-form-item :label="uiText('图形验证码')"><el-input v-model="captchaCode" :aria-label="uiText('图形验证码')" autocomplete="off" maxlength="5" :disabled="busy" /></el-form-item>
            <el-button :disabled="busy" @click="loadStatus">{{ uiText('刷新验证码') }}</el-button>
          </section>
          <el-button native-type="submit" type="primary" :loading="busy" :disabled="busy || (mfaRequired && !validOtp) || (captcha.required && !captchaCode.trim())">{{ uiText('验证并登录') }}</el-button>
        </el-form>
        <el-button v-if="!ready" type="primary" :loading="busy" :disabled="busy" @click="begin">{{ uiText('前往企业认证') }}</el-button>
        <section v-if="!ready && captcha.required" class="captcha-panel">
          <img :src="captcha.image" :alt="uiText('图形验证码')" width="180" height="64" />
          <label>{{ uiText('图形验证码') }}<el-input v-model="captchaCode" :aria-label="uiText('图形验证码')" autocomplete="off" maxlength="5" :disabled="busy" /></label>
          <el-button :disabled="busy" @click="loadStartCaptcha">{{ uiText('刷新验证码') }}</el-button>
        </section>
        <el-button v-else :disabled="busy" @click="restart">{{ uiText('重新开始企业认证') }}</el-button>
      </template>
      <p v-else-if="!error">{{ uiText('企业登录未启用，请使用本地账号登录。') }}</p>
      <el-button v-if="error && !ready" :disabled="loading || busy" @click="load">{{ uiText('重试配置') }}</el-button>
      <el-button class="local-entry" link :disabled="busy" @click="localLogin">{{ uiText('使用本地账号登录') }}</el-button>
    </section>
  </main>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ssoApi, type SSOLocalProof } from '@/api/sso'
import { type LoginCaptchaChallenge } from '@/api/loginCaptcha'
import { loginCaptchaApi } from '@/api/loginCaptcha'
import { useAuthStore } from '@/stores/auth'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { ssoMessages } from '@/i18n/ssoMessages'
import { getAccessToken } from '@/auth/tokenStorage'
registerUiMessages(ssoMessages)
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const loading = ref(false), busy = ref(false), enabled = ref(false), ready = ref(false), mfaRequired = ref(false), error = ref('')
const otpCode = ref(''), captchaCode = ref(''), captcha = ref<LoginCaptchaChallenge>({ required: false })
const validOtp = computed(() => /^(?:\d{6}|[0-9a-f]{32})$/.test(otpCode.value.trim()))
let controller: AbortController | undefined, alive = true
function failureText(failure: any) {
  const status = failure?.response?.status
  return uiText(status === 429 ? '尝试过于频繁，请稍后再试。' : status === 401 ? '企业登录确认已失效或认证码无效，请重试。' : '企业登录暂不可用，请使用本地登录或联系管理员。')
}
async function loadStatus() {
  if (busy.value || !alive) return
  try {
    const result = await ssoApi.status(controller?.signal)
    if (!alive) return
    ready.value = result.ready; mfaRequired.value = result.mfa_required; captcha.value = result.captcha; captchaCode.value = ''
  } catch (failure) { if (alive) { ready.value = false; error.value = failureText(failure) } }
}
async function loadStartCaptcha() {
  if (busy.value || !alive) return
  try { const result = await loginCaptchaApi.challenge('__oidc__', controller?.signal); if (alive) { captcha.value = result; captchaCode.value = '' } }
  catch (failure) { if (alive) error.value = failureText(failure) }
}
async function load() {
  controller?.abort(); const active = controller = new AbortController()
  loading.value = true; error.value = ''; enabled.value = false; ready.value = false
  try {
    const result = await ssoApi.config(active.signal)
    if (!alive || controller !== active) return
    enabled.value = result.enabled
    if (enabled.value && route.query.result === 'ready') await loadStatus()
    else if (enabled.value && route.query.result === 'failed') { error.value = uiText('企业身份授权未完成、未绑定或已失效，请重试或联系管理员。'); await loadStartCaptcha() }
    else if (enabled.value) await loadStartCaptcha()
  } catch (failure: any) { if (alive && !active.signal.aborted && failure?.response?.status !== 404) error.value = failureText(failure) }
  finally { if (alive && controller === active) loading.value = false }
}
async function begin() {
  if (busy.value || !enabled.value) return
  busy.value = true; error.value = ''
  try {
    if (captcha.value.required && !captchaCode.value.trim()) return
    const url = await ssoApi.start(captcha.value.required ? { captcha_id: captcha.value.challenge_id, captcha_code: captchaCode.value.trim() } : {}, controller?.signal)
    if (alive && !getAccessToken()) window.location.assign(url)
  } catch (failure) { if (alive) { error.value = failureText(failure); busy.value = false; await loadStartCaptcha() } }
  finally { if (alive) busy.value = false }
}
async function finish() {
  if (busy.value || !ready.value || (mfaRequired.value && !validOtp.value) || getAccessToken()) return
  busy.value = true; error.value = ''
  const proof: SSOLocalProof = { ...(mfaRequired.value ? { otp_code: otpCode.value.trim() } : {}), ...(captcha.value.required ? { captcha_id: captcha.value.challenge_id, captcha_code: captchaCode.value.trim() } : {}) }
  try { await auth.loginSSO(proof, controller?.signal); if (alive) { otpCode.value = ''; captchaCode.value = ''; await router.replace('/') } }
  catch (failure: any) {
    if (!alive) return
    otpCode.value = ''; error.value = failureText(failure)
    const code = failure?.response?.data?.data?.code
    if (code === 'mfa_required') mfaRequired.value = true
    // Re-check the server's pending flow and captcha without replaying the login POST.
    busy.value = false; await loadStatus()
  } finally { if (alive) busy.value = false }
}
async function restart() { if (!busy.value) { await ssoApi.cancel(controller?.signal).catch(() => {}); ready.value = false; otpCode.value = ''; captchaCode.value = ''; captcha.value = { required: false }; error.value = ''; await router.replace('/enterprise-login'); await loadStartCaptcha() } }
async function localLogin() { if (!busy.value) { await ssoApi.cancel(controller?.signal).catch(() => {}); await router.push('/login') } }
void load()
onBeforeUnmount(() => { alive = false; controller?.abort(); auth.cancelPendingLogin(); otpCode.value = ''; captchaCode.value = ''; captcha.value = { required: false } })
</script>
<style scoped>
.enterprise-login { min-height: 100vh; display: grid; place-items: center; padding: var(--spacing-lg); box-sizing: border-box; background: var(--color-bg-page); }
.login-panel { display: grid; gap: var(--spacing-lg); width: 100%; max-width: 420px; min-width: 0; padding: var(--spacing-xl); box-sizing: border-box; border: 1px solid var(--color-border); border-radius: var(--radius-xl); background: var(--color-bg-card); }
h1 { font-size: var(--font-size-xl); margin: 0; } p { margin: 0; line-height: 1.6; overflow-wrap: anywhere; color: var(--color-text-secondary); }
.el-button { min-height: 44px; margin-left: 0; white-space: normal; }
.el-form { display: grid; gap: var(--spacing-md); min-width: 0; }
.captcha-panel img { display: block; max-width: 100%; object-fit: contain; }
</style>
