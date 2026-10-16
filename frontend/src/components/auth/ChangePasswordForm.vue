<template>
  <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
    <div v-if="error" ref="errorRef" role="alert" tabindex="-1" class="password-error">{{ error }}</div>
    <el-form-item :label="uiText('当前密码')" prop="old">
      <el-input v-model="form.old" type="password" show-password autocomplete="current-password" :disabled="saving" />
    </el-form-item>
    <el-form-item :label="uiText('新密码')" prop="new1">
      <el-input v-model="form.new1" type="password" show-password autocomplete="new-password" :disabled="saving" />
    </el-form-item>
    <el-form-item :label="uiText('确认新密码')" prop="new2">
      <el-input v-model="form.new2" type="password" show-password autocomplete="new-password" :disabled="saving" />
    </el-form-item>
    <BaseButton variant="primary" native-type="submit" :loading="saving">{{ uiText('保存修改') }}</BaseButton>
  </el-form>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { BaseButton } from '@/components'
import { uiText } from '@/i18n/uiText'
import { useAuthStore } from '@/stores/auth'
import authApi from '@/api/auth'

const auth = useAuthStore()
const formRef = ref<FormInstance>()
const errorRef = ref<HTMLElement>()
const saving = ref(false)
const error = ref('')
const form = reactive({ old: '', new1: '', new2: '' })
const formGuard = useUnsavedChanges({ source: () => form, busy: () => saving.value, allowForcedPassword: true, clear: () => { form.old = ''; form.new1 = ''; form.new2 = '' } })
const rules = computed<FormRules>(() => ({
  old: [{ required: true, message: uiText('请填写当前密码和新密码'), trigger: 'blur' }],
  new1: [
    { required: true, message: uiText('请填写当前密码和新密码'), trigger: 'blur' },
    { min: 8, message: uiText('新密码至少 8 位'), trigger: 'blur' },
    { validator: (_rule, value, done) => done(value === form.old ? new Error(uiText('新密码不能与当前密码相同')) : undefined), trigger: 'blur' },
  ],
  new2: [{ validator: (_rule, value, done) => done(!value || value !== form.new1 ? new Error(uiText('两次输入的新密码不一致')) : undefined), trigger: 'blur' }],
}))

function failureText(failure: unknown): string {
  const data = responseData(failure)
  if (data && typeof data === 'object') {
    const body = data as { data?: unknown; message?: unknown }
    if (body.data && typeof body.data === 'object') {
      const values = Object.values(body.data as Record<string, unknown>).flatMap(value => Array.isArray(value) ? value : [value])
        .filter((value): value is string | number => typeof value === 'string' || typeof value === 'number')
      if (values.length) return values.join('；')
    }
    if (typeof body.message === 'string' && body.message) return body.message
  }
  return uiText('修改失败，请重试')
}

function responseData(failure: unknown): unknown {
  if (!failure || typeof failure !== 'object' || !('response' in failure)) return undefined
  const response: unknown = failure.response
  return response && typeof response === 'object' && 'data' in response ? response.data : undefined
}

async function submit() {
  if (saving.value) return
  error.value = ''
  saving.value = true
  try {
    if (!await formRef.value?.validate().catch(() => false)) return
    if (!formGuard.isCurrent()) return
    await authApi.changePassword(form.old, form.new1, form.new2)
    formGuard.discard()
    auth.clearSession()
    ElMessage.success(uiText('密码修改成功，请使用新密码重新登录'))
    window.location.assign('/login')
  } catch (failure: unknown) {
    error.value = failureText(failure)
    await nextTick()
    errorRef.value?.focus()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.password-error { color: var(--el-color-danger); margin-bottom: var(--spacing-lg); overflow-wrap: anywhere; }
</style>
