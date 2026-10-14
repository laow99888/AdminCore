<template>
  <main class="recovery-page">
    <BaseCard class="recovery-card">
      <h1>{{ uiText('找回密码') }}</h1>
      <p class="hint">{{ uiText('使用用户名和已验证邮箱申请邮件代码，再填写代码与新密码。') }}</p>
      <p v-if="loading" role="status">{{ uiText('正在检查找回密码配置') }}</p>
      <el-alert v-if="configError" :title="uiText('找回密码配置加载失败')" type="error" :closable="false" show-icon role="alert" />
      <BaseButton v-if="configError" size="large" @click="load">{{ uiText('重试找回配置') }}</BaseButton>
      <el-alert v-if="enabled === false" :title="uiText('邮件找回未启用，请联系管理员重置密码。')" type="info" :closable="false" show-icon />
      <template v-if="enabled">
        <div class="steps"><BaseButton size="large" :disabled="busy" :type="step === 'request' ? 'primary' : 'default'" :variant="step === 'request' ? 'primary' : 'ghost'" @click="changeStep('request')">{{ uiText('申请邮件代码') }}</BaseButton><BaseButton size="large" :disabled="busy" :type="step === 'reset' ? 'primary' : 'default'" :variant="step === 'reset' ? 'primary' : 'ghost'" @click="changeStep('reset')">{{ uiText('已有邮件代码') }}</BaseButton></div>
        <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon role="status" />
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
        <el-form v-if="step === 'request'" label-position="top" :disabled="busy" @submit.prevent="requestCode">
          <el-form-item :label="uiText('用户名')"><el-input v-model="username" :aria-label="uiText('用户名')" maxlength="150" autocomplete="username" /></el-form-item>
          <el-form-item :label="uiText('已验证邮箱')"><el-input v-model="email" :aria-label="uiText('已验证邮箱')" type="email" maxlength="254" autocomplete="email" /></el-form-item>
          <BaseButton size="large" variant="primary" type="primary" native-type="submit" :loading="busy" :disabled="busy || !username.trim() || !email.trim()">{{ uiText('提交找回申请') }}</BaseButton>
        </el-form>
        <el-form v-else label-position="top" :disabled="busy" @submit.prevent="resetPassword">
          <p class="hint">{{ uiText('请粘贴邮件中的完整代码。代码有时效且只能使用一次。') }}</p>
          <el-form-item :label="uiText('邮件代码')"><el-input v-model="code" :aria-label="uiText('邮件代码')" autocomplete="off" maxlength="97" /></el-form-item>
          <el-form-item :label="uiText('新密码')"><el-input v-model="password" :aria-label="uiText('新密码')" type="password" show-password autocomplete="new-password" maxlength="1024" /></el-form-item>
          <el-form-item :label="uiText('确认新密码')"><el-input v-model="password2" :aria-label="uiText('确认新密码')" type="password" show-password autocomplete="new-password" maxlength="1024" /></el-form-item>
          <BaseButton size="large" variant="primary" type="primary" native-type="submit" :loading="busy" :disabled="busy || !code.trim() || !password || !password2">{{ uiText('重置密码') }}</BaseButton>
        </el-form>
        <BaseButton size="large" variant="ghost" :disabled="busy" @click="cancel">{{ uiText('取消并返回登录') }}</BaseButton>
      </template>
      <BaseButton v-else size="large" variant="ghost" :disabled="loading" @click="cancel">{{ uiText('返回登录') }}</BaseButton>
    </BaseCard>
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { BaseButton, BaseCard } from '@/components'
import { recoveryApi, passwordResetError } from '@/api/recovery'
import { uiText } from '@/i18n/uiText'

const router = useRouter()
const loading = ref(false), busy = ref(false), enabled = ref<boolean | null>(null), configError = ref(false)
const step = ref<'request' | 'reset'>('request'), username = ref(''), email = ref(''), code = ref(''), password = ref(''), password2 = ref(''), error = ref(''), notice = ref('')
let alive = true, controller: AbortController | undefined
function clearSecrets() { code.value = ''; password.value = ''; password2.value = '' }
function clear() { clearSecrets(); username.value = ''; email.value = '' }
async function load() {
  controller?.abort(); controller = new AbortController(); const current = controller
  loading.value = true; configError.value = false; enabled.value = null
  try { const value = await recoveryApi.config(current.signal); if (alive && !current.signal.aborted) enabled.value = value.enabled }
  catch { if (alive && !current.signal.aborted) configError.value = true }
  finally { if (alive && !current.signal.aborted) loading.value = false }
}
function changeStep(value: 'request' | 'reset') { if (!busy.value) { clearSecrets(); error.value = ''; step.value = value } }
async function requestCode() {
  if (busy.value || !enabled.value || !username.value.trim() || !email.value.trim()) return
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) { error.value = uiText('请输入有效邮箱'); return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await recoveryApi.request(username.value.trim(), email.value.trim())
    if (alive) { clear(); step.value = 'reset'; notice.value = uiText('申请已提交；若账号与已验证邮箱匹配，将异步发送邮件，请稍后查收。') }
  } catch { if (alive) error.value = uiText('找回申请未确认，请稍后重试。') }
  finally { if (alive) busy.value = false }
}
async function resetPassword() {
  if (busy.value || !enabled.value || !code.value.trim() || !password.value || !password2.value) return
  if (!/^[a-f0-9]{32}\.[a-f0-9]{64}$/.test(code.value.trim())) { error.value = uiText('请输入邮件中的完整代码'); return }
  if (password.value !== password2.value) { error.value = uiText('两次输入的新密码不一致'); return }
  busy.value = true; error.value = ''; notice.value = ''
  const payload = [code.value.trim(), password.value, password2.value] as const
  clearSecrets()
  try {
    await recoveryApi.reset(...payload)
    if (alive) { clear(); notice.value = uiText('密码已重置，请返回登录。'); step.value = 'request' }
  } catch (reason) { if (alive) error.value = passwordResetError(reason) ?? uiText('重置未确认，代码可能无效或过期；请重新填写或申请邮件。') }
  finally { if (alive) busy.value = false }
}
function cancel() { if (!busy.value) { clear(); void router.push('/login') } }
onBeforeRouteLeave(() => { if (busy.value) return false; clear(); return true })
void load()
onBeforeUnmount(() => { alive = false; controller?.abort(); clear() })
</script>

<style scoped>
.recovery-page { min-height: 100vh; display: grid; place-items: center; padding: var(--spacing-lg); background: var(--color-bg-page); }
.recovery-card { width: 100%; max-width: 520px; min-width: 0; }
h1 { margin: 0 0 var(--spacing-lg); font-size: var(--font-size-xl); }
p { overflow-wrap: anywhere; line-height: 1.6; }
.hint { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.steps { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); margin: var(--spacing-lg) 0; }
:deep(.el-alert), :deep(.base-button) { margin-bottom: var(--spacing-md); }
</style>
