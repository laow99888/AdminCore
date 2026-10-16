<template>
  <section class="email-verification" :aria-label="uiText('邮箱验证')">
    <p>{{ uiText('邮箱验证') }}: <strong>{{ uiText(profile.email_verified ? '已验证' : '未验证') }}</strong></p>
    <p v-if="changed" class="hint">{{ uiText('邮箱修改尚未保存；保存后需重新验证。') }}</p>
    <p v-else-if="!profile.email" class="hint">{{ uiText('请先保存非空邮箱，再申请验证。') }}</p>
    <p v-else-if="!profile.recovery_enabled" class="hint">{{ uiText('邮件找回未启用，请联系管理员重置密码。') }}</p>
    <template v-if="available && !profile.email_verified">
      <p class="hint">{{ uiText('验证邮件只发送到已保存邮箱：{p0}', { p0: profile.email }) }}</p>
      <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon role="status" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-form label-position="top" :disabled="busy || disabled" @submit.prevent="send">
        <el-form-item :label="uiText('邮箱验证当前密码')"><el-input v-model="password" :aria-label="uiText('邮箱验证当前密码')" type="password" show-password autocomplete="current-password" maxlength="1024" /></el-form-item>
        <el-button native-type="submit" :loading="sending" :disabled="busy || disabled || !password">{{ uiText('申请邮箱验证') }}</el-button>
      </el-form>
      <el-form label-position="top" :disabled="busy || disabled" @submit.prevent="confirm">
        <el-form-item :label="uiText('邮箱验证代码')"><el-input v-model="code" :aria-label="uiText('邮箱验证代码')" autocomplete="off" maxlength="97" /></el-form-item>
        <div class="actions"><el-button native-type="submit" :loading="confirming" :disabled="busy || disabled || !code.trim()">{{ uiText('确认邮箱验证') }}</el-button><el-button :disabled="busy || disabled" @click="cancel">{{ uiText('取消邮箱验证') }}</el-button></div>
      </el-form>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import authApi, { type PersonalProfile } from '@/api/auth'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { emailVerificationMessages } from '@/i18n/emailVerificationMessages'
import { getAccessToken } from '@/auth/tokenStorage'
registerUiMessages(emailVerificationMessages)
const props = defineProps<{ profile: PersonalProfile; changed: boolean; disabled: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; updated: [profile: PersonalProfile]; conflict: [] }>()
const password = ref(''), code = ref(''), notice = ref(''), error = ref(''), sending = ref(false), confirming = ref(false)
const busy = computed(() => sending.value || confirming.value)
const available = computed(() => !!props.profile.recovery_enabled && !!props.profile.email && !props.changed)
let alive = true
function clear() { password.value = ''; code.value = '' }
function cancel() { if (!busy.value) { clear(); notice.value = ''; error.value = '' } }
watch(() => [props.profile.email, props.profile.email_verified, props.changed], () => { clear(); notice.value = ''; error.value = '' })
async function send() {
  if (busy.value || props.disabled || !available.value || !password.value) return
  const token = getAccessToken(), supplied = password.value
  password.value = ''; sending.value = true; emit('busy', true); error.value = ''; notice.value = ''
  try {
    await authApi.requestEmailVerification(supplied)
    if (alive && tokensBelongToSameSession(token, getAccessToken())) notice.value = uiText('验证申请已提交，邮件由后台异步发送，请稍后查收。')
  } catch { if (alive && tokensBelongToSameSession(token, getAccessToken())) error.value = uiText('邮箱验证申请未确认，请重新输入密码后重试。') }
  finally { if (alive) { sending.value = false; emit('busy', false) } }
}
async function confirm() {
  if (busy.value || props.disabled || !available.value || !code.value.trim()) return
  if (!/^[a-f0-9]{32}\.[a-f0-9]{64}$/.test(code.value.trim())) { error.value = uiText('请输入邮件中的完整代码'); return }
  const token = getAccessToken(), supplied = code.value.trim(), savedEmail = props.profile.email, version = props.profile.profile_version
  code.value = ''; confirming.value = true; emit('busy', true); error.value = ''; notice.value = ''
  try {
    const value = await authApi.confirmEmailVerification(supplied)
    if (alive && tokensBelongToSameSession(token, getAccessToken())) {
      if (value.email !== savedEmail || value.profile_version !== version + 1 || !value.email_verified) { emit('conflict'); return }
      emit('updated', value)
    }
  } catch { if (alive && tokensBelongToSameSession(token, getAccessToken())) error.value = uiText('邮箱验证未确认，代码可能无效或过期；请重新填写或申请邮件。') }
  finally { if (alive) { confirming.value = false; emit('busy', false) } }
}
onBeforeUnmount(() => { alive = false; clear() })
</script>

<style scoped>
.email-verification { margin: var(--spacing-lg) 0; padding: var(--spacing-md) 0; border-top: 1px solid var(--color-border); }
.hint { font-size: var(--font-size-sm); color: var(--color-text-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); }
:deep(.el-form) { margin-top: var(--spacing-md); }
</style>
