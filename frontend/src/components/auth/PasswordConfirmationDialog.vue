<template>
  <BaseDialog v-model="visible" :title="uiText('密码二次确认')" width="480px" :loading="busy" :confirm-disabled="!password || disabled" :confirm-text="confirmText || uiText('确认下线')" @confirm="submit" @close="clear">
    <p class="confirmation-description">{{ description }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <el-form @submit.prevent="submit">
      <el-form-item :label="uiText('当前密码')">
        <el-input v-model="password" type="password" show-password autocomplete="current-password" :disabled="busy" :aria-label="uiText('当前密码')" maxlength="4096" />
      </el-form-item>
    </el-form>
    <p class="password-hint">{{ uiText('密码仅用于本次确认；提交后立即清空。') }}</p>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { BaseDialog } from '@/components'
import { uiText } from '@/i18n/uiText'

const props = defineProps<{ modelValue: boolean; description: string; execute: (password: string) => Promise<void>; disabled?: boolean; confirmText?: string; errorText?: string; allowRouteLeave?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; 'busy': [value: boolean] }>()
const password = ref(''), busy = ref(false), error = ref('')
let alive = true
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
function clear() { password.value = ''; error.value = '' }
watch(() => props.modelValue, () => clear())
async function submit() {
  if (!props.modelValue || busy.value || props.disabled || !password.value) return
  const suppliedPassword = password.value
  password.value = ''; error.value = ''; busy.value = true; emit('busy', true)
  try {
    await props.execute(suppliedPassword)
    if (alive) emit('update:modelValue', false)
  } catch {
    if (alive && props.modelValue) error.value = props.errorText || uiText('下线未确认，请检查密码与权限后重新输入并重试。')
  } finally {
    if (alive) { busy.value = false; emit('busy', false) }
  }
}
onBeforeRouteLeave(() => props.allowRouteLeave || !busy.value || !localStorage.getItem('token'))
onBeforeUnmount(() => { alive = false; clear() })
</script>

<style scoped>
.confirmation-description { overflow-wrap: anywhere; line-height: 1.6; }
.password-hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
:deep(.el-form) { margin-top: var(--spacing-lg); }
</style>
