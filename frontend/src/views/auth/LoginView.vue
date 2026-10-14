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
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
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
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
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
          <el-form-item class="mb-0">
            <el-button
              type="primary"
              class="login-btn"
              :loading="loading"
              @click="handleLogin"
            >{{ uiText("登录") }}</el-button>
          </el-form-item>
        </el-form>
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

import { onBeforeUnmount, ref } from 'vue'
import { recoveryApi } from '@/api/recovery'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from 'lucide-vue-next'
import { useAuthStore } from '../../stores/auth'
import { useBrandStore } from '@/stores/brand'

const router = useRouter()
const authStore = useAuthStore()
const brand = useBrandStore()
const loading = ref(false)
const focusedField = ref('')
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
onBeforeUnmount(() => { alive = false; recoveryController?.abort(); form.value.password = '' })

const form = ref({
  username: '',
  password: '',
})

const handleLogin = async () => {
  if (loading.value) return
  if (!form.value.username || !form.value.password) {
    ElMessage.error(uiText("请输入用户名和密码"))
    return
  }

  loading.value = true
  try {
    await authStore.login(form.value.username, form.value.password)
    ElMessage.success(uiText("登录成功"))
    router.push('/')
  } catch (error: any) {
    const message = error?.response?.data?.message
    if (message && error?.response?.status !== 401) {
      ElMessage.error(message)
    } else {
      ElMessage.error(uiText("用户名或密码错误"))
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  width: 100%;
  height: 100vh;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #f9fafb 0%, rgba(240, 253, 250, 0.3) 50%, #f3f4f6 100%);
}

.dark .login-container {
  background: linear-gradient(135deg, #020617 0%, #0f172a 100%);
}

/* 背景装饰 */
.login-background {
  position: absolute;
  width: 100%;
  height: 100%;
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
