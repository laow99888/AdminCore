<template>
  <div v-if="loading" role="status">{{ uiText('正在加载个人资料') }}</div>
  <div v-else-if="!profile" role="alert">
    <p>{{ uiText('个人资料加载失败') }}</p>
    <el-button @click="load">{{ uiText('重试') }}</el-button>
  </div>
  <div v-else class="profile-editor">
    <div class="profile-heading">
      <div class="profile-avatar"><PrivateAvatar :icon-size="30" /></div>
      <strong>{{ profile.username }}</strong>
    </div>
    <p class="hint">{{ uiText('PNG、JPEG 或 WebP，不超过 5 MiB、400 万像素；自动裁剪为 256×256 PNG。') }}</p>
    <p v-if="!profile.avatar_enabled" class="hint">{{ uiText('文件模块未启用，头像操作不可用') }}</p>
    <div class="actions">
      <input ref="fileInput" type="file" accept=".png,.jpg,.jpeg,.webp" class="file-input" :aria-label="uiText('选择头像文件')" :disabled="busy || !profile.avatar_enabled" @change="upload" />
      <el-button :disabled="busy || !profile.avatar_enabled" @click="fileInput?.click()">{{ uiText('上传头像') }}</el-button>
      <el-button :disabled="busy || !profile.avatar_enabled || !profile.has_avatar" @click="remove">{{ uiText('删除头像') }}</el-button>
    </div>
    <div v-if="auth.avatarError" role="alert" class="hint">
      {{ uiText('头像加载失败') }}
      <el-button text :disabled="auth.avatarLoading" @click="auth.loadAvatar">{{ uiText('重试') }}</el-button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <el-button v-if="conflict" :disabled="busy" @click="reload">{{ uiText('重新加载资料') }}</el-button>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" :disabled="busy" @submit.prevent="save">
      <el-form-item :label="uiText('姓氏')" prop="last_name"><el-input v-model="form.last_name" :maxlength="150" :aria-label="uiText('姓氏')" /></el-form-item>
      <el-form-item :label="uiText('名字')" prop="first_name"><el-input v-model="form.first_name" :maxlength="150" :aria-label="uiText('名字')" /></el-form-item>
      <el-form-item :label="uiText('邮箱')" prop="email"><el-input v-model="form.email" type="email" :maxlength="254" :aria-label="uiText('邮箱')" /></el-form-item>
      <el-form-item :label="uiText('电话')" prop="phone"><el-input v-model="form.phone" :maxlength="20" :aria-label="uiText('电话')" /></el-form-item>
      <el-form-item :label="uiText('个人简介')" prop="bio"><el-input v-model="form.bio" type="textarea" :rows="3" :maxlength="1000" show-word-limit :aria-label="uiText('个人简介')" /></el-form-item>
      <div class="actions">
        <el-button type="primary" native-type="submit" :loading="busy" :disabled="!dirty || conflict">{{ uiText('保存资料') }}</el-button>
        <el-button :disabled="busy || !dirty" @click="discard">{{ uiText('撤销修改') }}</el-button>
      </div>
    </el-form>
    <EmailVerification :profile="profile" :changed="form.email !== profile.email" :disabled="busy || conflict" @busy="verificationBusy = $event" @updated="verificationUpdated" @conflict="verificationConflict" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import authApi, { type PersonalProfile, type ProfileWrite } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'
import PrivateAvatar from './PrivateAvatar.vue'
import EmailVerification from './EmailVerification.vue'

const auth = useAuthStore()
const profile = ref<PersonalProfile>()
const loading = ref(false)
const writing = ref(false), verificationBusy = ref(false)
const busy = computed({ get: () => writing.value || verificationBusy.value, set: value => { writing.value = value } })
const error = ref('')
const conflict = ref(false)
const fileInput = ref<HTMLInputElement>()
const formRef = ref<FormInstance>()
const form = reactive({ first_name: '', last_name: '', email: '', phone: '', bio: '' })
let request: AbortController | undefined
let alive = true
const formGuard = useUnsavedChanges({ source: () => form, active: () => !!profile.value, busy: () => busy.value, message: () => uiText('尚有未保存的资料，确定放弃修改吗？'), clear: () => { for (const field of Object.keys(form) as Array<keyof typeof form>) form[field] = '' } })
const dirty = formGuard.dirty
const canApply = (value: PersonalProfile) => alive && auth.isAuthenticated && auth.user?.id === value.id
const rules = computed<FormRules>(() => ({
  email: [{ type: 'email', message: uiText('请输入有效邮箱'), trigger: 'blur' }],
  phone: [{ pattern: /^$|^\+?[0-9 ()-]{3,20}$/, message: uiText('请输入有效电话'), trigger: 'blur' }],
}))

function apply(value: PersonalProfile, reset = true) {
  profile.value = value
  auth.applyUser(value)
  if (reset) {
    for (const field of Object.keys(form) as Array<keyof typeof form>) form[field] = value[field]
    formGuard.markClean()
    formRef.value?.clearValidate()
  }
}
function verificationUpdated(value: PersonalProfile) { if (canApply(value)) apply(value, false) }
function verificationConflict() { conflict.value = true; error.value = uiText('资料已被其他窗口修改，当前输入已保留，请重新加载。') }
async function load() {
  request?.abort()
  const current = new AbortController()
  request = current
  loading.value = true; error.value = ''; conflict.value = false
  try {
    const value = await authApi.profile(current.signal)
    if (!value || !Number.isInteger(value.profile_version) || value.profile_version < 1
      || Object.keys(form).some(field => typeof value[field as keyof PersonalProfile] !== 'string')) throw new Error('Invalid profile')
    if (canApply(value) && !current.signal.aborted) apply(value)
  } catch {
    if (alive && !current.signal.aborted) profile.value = undefined
  } finally {
    if (alive && !current.signal.aborted) loading.value = false
  }
}
const confirmDiscard = formGuard.confirmDiscard
async function reload() { if (await confirmDiscard()) await load() }
async function discard() { if (profile.value && await confirmDiscard()) apply(profile.value) }
function failed(reason: unknown) {
  conflict.value = (reason as { response?: { status?: number } })?.response?.status === 409
  error.value = uiText(conflict.value ? '资料已被其他窗口修改，当前输入已保留，请重新加载。' : '操作失败，请检查输入或稍后重试。')
}
async function save() {
  if (busy.value || !profile.value || conflict.value) return
  busy.value = true; error.value = ''
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    if (!formGuard.isCurrent() || !profile.value) return
    const value = await authApi.saveProfile({ ...form, profile_version: profile.value.profile_version } satisfies ProfileWrite)
    if (canApply(value)) { apply(value); ElMessage.success(uiText('资料已保存')) }
  } catch (reason) { if (alive) failed(reason) }
  finally { busy.value = false }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || busy.value || !profile.value?.avatar_enabled) return
  if (!/\.(png|jpe?g|webp)$/i.test(file.name) || file.size === 0 || file.size > 5 * 1024 * 1024) {
    error.value = uiText('请选择不超过 5 MiB 的 PNG、JPEG 或 WebP 图片'); return
  }
  busy.value = true; error.value = ''
  try {
    const value = await authApi.uploadAvatar(file, profile.value.profile_version)
    if (canApply(value)) { apply(value, false); ElMessage.success(uiText('头像已更新')) }
  } catch (reason) { if (alive) failed(reason) }
  finally { busy.value = false }
}
async function remove() {
  if (busy.value || !profile.value?.avatar_enabled || !profile.value.has_avatar) return
  try {
    await ElMessageBox.confirm(uiText('确定删除当前头像吗？'), uiText('提示'), { confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), type: 'warning' })
  } catch { return }
  if (busy.value || !profile.value) return
  busy.value = true; error.value = ''
  try {
    const value = await authApi.removeAvatar(profile.value.profile_version)
    if (canApply(value)) { apply(value, false); ElMessage.success(uiText('头像已删除')) }
  } catch (reason) { if (alive) failed(reason) }
  finally { busy.value = false }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { alive = false; request?.abort() })
</script>

<style scoped>
.profile-heading { display: flex; align-items: center; gap: var(--spacing-lg); }
.profile-heading strong { overflow-wrap: anywhere; }
.profile-avatar { width: 64px; height: 64px; flex-shrink: 0; background: var(--color-bg-elevated); border-radius: 50%; }
.hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); line-height: 1.6; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.actions :deep(.el-button + .el-button) { margin-left: 0; }
.file-input { display: none; }
</style>
