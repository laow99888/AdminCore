<template>
  <div class="login-container">
    <div class="login-background"></div>
    <div class="login-content flex-center">
      <div class="login-card">
        <div class="card-header text-center">
          <img v-if="brand.logo" :src="brand.logo" :alt="brand.name" class="brand-logo" />
          <h1 class="title">{{ brand.name }}</h1>
          <p class="subtitle">{{ uiText(brand.tagline) }}</p>
        </div>
        <el-form ref="formRef" :model="form" :disabled="loading" @submit.prevent="handleLogin" @keyup.enter="handleLogin" class="login-form">
          <el-form-item prop="username" :label="uiText('用户名')" label-position="top">
            <el-input
              v-model="form.username"
              :aria-label="uiText('用户名')"
              autocomplete="username"
              :disabled="loading || mfaRequired"
              :placeholder="uiText('用户名')"
              clearable
              @focus="focusedField = 'username'"
              @blur="focusedField = ''"
            >
              <template #prefix>
                <User :size="16" :stroke-width="1.75" class="input-icon" />
              </template>
            </el-input>
          </el-form-item>
          <el-form-item prop="password" :label="uiText('密码')" label-position="top">
            <el-input
              v-model="form.password"
              :aria-label="uiText('密码')"
              autocomplete="current-password"
              :disabled="loading || mfaRequired"
              type="password"
              :placeholder="uiText('密码')"
              clearable
              show-password
              @focus="focusedField = 'password'"
              @blur="focusedField = ''"
            >
              <template #prefix>
                <Lock :size="16" :stroke-width="1.75" class="input-icon" />
              </template>
            </el-input>
          </el-form-item>
          <section v-if="captcha.required.value" class="captcha-panel" :aria-label="uiText('登录安全验证')">
            <p class="captcha-hint">{{ uiText('请输入图片中的 5 位字母或数字；无法识别时可刷新，仍无法完成请联系管理员。') }}</p>
            <p v-if="captcha.loading.value" role="status">{{ uiText('正在加载验证码') }}</p>
            <p v-else-if="captcha.error.value" role="alert">{{ uiText(captcha.error.value === 'expired' ? '验证码已过期，请刷新后重试。' : captcha.error.value === 'image' ? '验证码图片无法显示，请刷新或联系管理员。' : '验证码加载失败，请刷新重试。') }}</p>
            <template v-if="captcha.challenge.value">
              <img :src="captcha.challenge.value.image" :alt="uiText('登录验证码图片')" class="captcha-image" @error="captcha.imageFailed" />
              <p aria-live="off">{{ uiText('验证码有效期剩余 {p0} 秒', { p0: captcha.seconds.value }) }}</p>
            </template>
            <el-form-item class="captcha-code-item" label-position="top" :label="uiText('图形验证码')"><el-input v-model="captcha.code.value" :aria-label="uiText('图形验证码')" :disabled="loading || !captcha.ready.value" autocomplete="off" autocapitalize="characters" maxlength="5" /></el-form-item>
            <el-button :disabled="loading || captcha.loading.value" @click="captcha.refresh">{{ uiText('刷新验证码') }}</el-button>
          </section>
          <template v-if="mfaRequired">
            <p role="status">{{ uiText('请填写认证器的 6 位动态码或一次性恢复码。') }}</p>
            <el-form-item class="otp-code-item" label-position="top" :label="uiText('动态码或恢复码')"><el-input v-model="otpCode" :aria-label="uiText('动态码或恢复码')" autocomplete="one-time-code" maxlength="64" /></el-form-item>
            <el-button :disabled="loading" @click="cancelMfa">{{ uiText('取消双因素登录') }}</el-button>
          </template>
          <el-form-item class="mb-0">
            <el-button
              type="primary"
              class="login-btn"
              :loading="loading"
              :disabled="captcha.required.value && !captcha.ready.value"
              @click="handleLogin"
            >{{ uiText(mfaRequired ? '验证并登录' : '登录') }}</el-button>
          </el-form-item>
        </el-form>
        <component :is="SSOEntry" v-if="SSOEntry" :disabled="loading" />
        <div class="recovery-entry">
          <el-button v-if="recoveryEnabled" link :disabled="loading" @click="router.push('/recover-password')">{{ uiText('忘记密码') }}</el-button>
          <span v-else-if="recoveryLoading" role="status">{{ uiText('正在检查找回密码配置') }}</span>
          <template v-else-if="recoveryError"><span>{{ uiText('找回密码配置加载失败') }}</span><el-button link :disabled="loading" @click="loadRecovery">{{ uiText('重试找回配置') }}</el-button></template>
          <span v-else>{{ uiText('邮件找回未启用，请联系管理员重置密码。') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { defineAsyncComponent, onBeforeUnmount, ref } from 'vue'
import { recoveryApi } from '@/api/recovery'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from 'lucide-vue-next'
import { useAuthStore } from '../../stores/auth'
import { useBrandStore } from '@/stores/brand'
import { useLoginCaptcha } from '@/composables/useLoginCaptcha'

const router = useRouter()
const SSOEntry = __ADMINCORE_MINIMAL_BUILD__ ? null : defineAsyncComponent(() => import('@/components/auth/SSOEntry.vue'))
const authStore = useAuthStore()
const brand = useBrandStore()
const loading = ref(false)
const focusedField = ref('')
const mfaRequired = ref(false), otpCode = ref('')
function cancelMfa() { if (!loading.value) { mfaRequired.value = false; otpCode.value = ''; form.value.password = ''; captcha.clear() } }
const recoveryEnabled = ref(false), recoveryLoading = ref(false), recoveryError = ref(false)
let recoveryController: AbortController | undefined, alive = true
async function loadRecovery() {
  recoveryController?.abort()
  const controller = new AbortController(); recoveryController = controller
  recoveryLoading.value = true; recoveryError.value = false; recoveryEnabled.value = false
  try { const result = await recoveryApi.config(controller.signal); if (alive && !controller.signal.aborted) recoveryEnabled.value = result.enabled }
  catch { if (alive && !controller.signal.aborted) recoveryError.value = true }
  finally { if (alive && !controller.signal.aborted) recoveryLoading.value = false }
}
void loadRecovery()
onBeforeUnmount(() => { alive = false; authStore.cancelPendingLogin(); recoveryController?.abort(); form.value.password = ''; otpCode.value = '' })

const form = ref({
  username: '',
  password: '',
})
const captcha = useLoginCaptcha(() => form.value.username)

function responseOf(failure: unknown): { status?: number; data?: unknown } | undefined {
  if (!failure || typeof failure !== 'object' || !('response' in failure)) return undefined
  const response: unknown = failure.response
  if (!response || typeof response !== 'object') return undefined
  const status = 'status' in response && typeof response.status === 'number' ? response.status : undefined
  const data = 'data' in response ? response.data : undefined
  return { status, data }
}

const handleLogin = async () => {
  if (loading.value) return
  if (!form.value.username || !form.value.password) {
    ElMessage.error(uiText("请输入用户名和密码"))
    return
  }
  if (mfaRequired.value && !otpCode.value.trim()) { ElMessage.error(uiText('请填写动态码或恢复码')); return }
  const proof = captcha.proof()
  if (captcha.required.value && !proof) { ElMessage.error(uiText('请填写有效的图形验证码')); return }

  loading.value = true
  if (proof) captcha.consume()
  let reloadCaptcha = !!proof
  try {
    await authStore.login(form.value.username, form.value.password, mfaRequired.value ? otpCode.value.trim() : undefined, proof)
    if (!alive) return
    reloadCaptcha = false; captcha.clear()
    form.value.password = ''; otpCode.value = ''; mfaRequired.value = false
    ElMessage.success(uiText("登录成功"))
    router.push('/')
  } catch (error: unknown) {
    if (!alive) return
    const response = responseOf(error)
    const payload = response?.data && typeof response.data === 'object' ? response.data as Record<string, unknown> : undefined
    const nested = payload?.data && typeof payload.data === 'object' ? payload.data as Record<string, unknown> : undefined
    const captchaReason = (typeof nested?.code === 'string' ? nested.code : undefined) ?? (typeof payload?.code === 'string' ? payload.code : undefined)
    if ([400, 401].includes(response?.status ?? 0) && ['captcha_required', 'captcha_invalid'].includes(captchaReason ?? '')) {
      reloadCaptcha = true
      if (mfaRequired.value) otpCode.value = ''
      ElMessage.error(uiText(captchaReason === 'captcha_required' ? '本次登录需要图形验证码，请填写后重试。' : '图形验证码无效或已过期，请使用新图片重试。'))
      return
    }
    if (!mfaRequired.value && [429, 503].includes(response?.status ?? 0)) {
      ElMessage.error(uiText(response?.status === 429 ? '尝试过于频繁，请稍后再试。' : '登录服务暂不可用，请稍后重试或联系管理员。'))
      return
    }
    if (!response) { ElMessage.error(uiText('登录未确认，请稍后重试。')); return }
    if (response.status === 401 && (payload?.code === 'mfa_required' || nested?.code === 'mfa_required')) { mfaRequired.value = true; otpCode.value = ''; return }
    if (mfaRequired.value) {
      otpCode.value = ''
      const status = response.status
      ElMessage.error(uiText(status === 503 ? '双因素认证服务暂不可用，请联系管理员或稍后重试。' : status === 429 ? '尝试过于频繁，请稍后再试。' : status === 401 ? '动态码或恢复码无效，请重试' : '登录未确认，请稍后重试。'))
      return
    }
    const message = typeof payload?.message === 'string' ? payload.message : undefined
    if (message && response.status !== 401) {
      ElMessage.error(message)
    } else {
      ElMessage.error(uiText("用户名或密码错误"))
    }
  } finally {
    if (alive) { loading.value = false; if (reloadCaptcha) void captcha.refresh() }
  }
}
</script>

<style scoped>
.login-container {
  width: 100%;
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
  background: linear-gradient(135deg, #f9fafb 0%, rgba(240, 253, 250, 0.3) 50%, #f3f4f6 100%);
}

.dark .login-container {
  background: linear-gradient(135deg, #020617 0%, #0f172a 100%);
}

/* 背景装饰 */
.login-background {
  position: absolute;
  width: 100%;
  min-height: 100vh;
  padding: var(--spacing-lg);
  box-sizing: border-box;
  pointer-events: none;
}

.login-background::before,
.login-background::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  opacity: 0.1;
  filter: blur(80px);
}

.login-background::before {
  width: 400px;
  height: 400px;
  top: 10%;
  right: 5%;
  background: var(--color-primary-500);
}

.login-background::after {
  width: 300px;
  height: 300px;
  bottom: 5%;
  left: 5%;
  background: var(--color-primary-500);
}

.dark .login-background::before,
.dark .login-background::after {
  opacity: 0.05;
}

/* 登录内容 */
.login-content {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
}

.login-card {
  width: 100%;
  max-width: 380px;
  padding: var(--spacing-2xl);
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-2xl);
  border: 1px solid var(--color-border);
  backdrop-filter: blur(10px);
}

.card-header {
  margin-bottom: var(--spacing-2xl);
}

.title {
  overflow-wrap: anywhere;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  margin: 0 0 var(--spacing-sm);
  background: linear-gradient(135deg, var(--color-primary-500) 0%, #64748b 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  overflow-wrap: anywhere;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.login-form {
  margin-top: var(--spacing-2xl);
}
.brand-logo { width: 64px; height: 64px; object-fit: contain; margin-bottom: var(--spacing-md); }
.captcha-panel { margin-bottom: var(--spacing-lg); min-width: 0; }
.captcha-code-item, .otp-code-item { width: 100%; }
.captcha-hint, .captcha-panel p { font-size: var(--font-size-sm); color: var(--color-text-secondary); overflow-wrap: anywhere; line-height: 1.5; }
.captcha-image { display: block; width: 200px; height: 64px; max-width: 100%; object-fit: contain; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.recovery-entry { margin-top: var(--spacing-lg); font-size: var(--font-size-sm); color: var(--color-text-secondary); text-align: center; overflow-wrap: anywhere; }

.input-icon {
  margin-right: var(--spacing-sm);
}

.login-btn {
  width: 100%;
  height: 40px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
  border: none;
  transition: all var(--transition-fast);
}

.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px color-mix(in srgb, var(--color-primary-500) 30%, transparent);
}

.login-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.mb-0 {
  margin-bottom: 0;
}

:deep(.el-form-item) {
  margin-bottom: var(--spacing-lg);
}

:deep(.el-input__wrapper) {
  background-color: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
}

:deep(.el-input__wrapper:hover) {
  border-color: var(--color-primary-500);
}
</style>
