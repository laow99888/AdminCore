<template>
  <PasswordConfirmationDialog v-if="!values" v-model="confirming" :description="uiText('查看 {p0} 的邮箱和电话原值；需要本次密码确认，查看会记录审计日志。', { p0: target.username })" :execute="reveal" :confirm-text="uiText('确认查看')" :error-text="uiText('原值查看未确认，请检查密码与权限后重新输入并重试。')" :allow-route-leave="true" />
  <BaseDialog v-else :model-value="true" :title="uiText('敏感字段原值')" width="480px" :show-cancel="false" :confirm-text="uiText('关闭并清除')" @update:model-value="close" @confirm="close">
    <p>{{ target.username }}</p>
    <p>{{ uiText('原值仅临时展示，60 秒后自动清除；关闭窗口也会立即清除。') }}</p>
    <dl class="sensitive-values" data-sensitive-values>
      <dt>{{ uiText('邮箱') }}</dt><dd>{{ values.email || uiText('未填写') }}</dd>
      <dt>{{ uiText('电话') }}</dt><dd>{{ values.phone || uiText('未填写') }}</dd>
    </dl>
  </BaseDialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PasswordConfirmationDialog from './PasswordConfirmationDialog.vue'
import { BaseDialog } from '@/components'
import { usersApi } from '@/api'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'
import { getAccessToken } from '@/auth/tokenStorage'

const props = defineProps<{ target: { id: string; username: string } }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), confirming = ref(true)
const values = ref<{ email: string; phone: string }>()
const ownerToken = getAccessToken(), owner = auth.user?.id
let alive = true, controller: AbortController | undefined, timer: number | undefined
let expiresAt = 0
const current = () => alive && auth.user?.id === owner && auth.can('user:read') && auth.can('user:sensitive_read') && tokensBelongToSameSession(ownerToken, getAccessToken())
function clear() { values.value = undefined; expiresAt = 0; controller?.abort(); window.clearTimeout(timer) }
function close() { clear(); emit('close') }
async function reveal(password: string) {
  if (!current()) { close(); return }
  controller = new AbortController()
  const active = controller
  const result = await usersApi.sensitive(props.target.id, password, active.signal)
  if (!current() || active.signal.aborted) return
  values.value = { email: result.email, phone: result.phone }
  expiresAt = Date.now() + 60_000
  timer = window.setTimeout(close, 60_000)
}
watch(confirming, value => { if (!value && !values.value) close() })
watch(() => [auth.token, auth.user?.id, auth.user?.permissions], () => { if (!current()) close() }, { deep: true, flush: 'sync' })
function storageChanged(event: StorageEvent) { if ((event.key === 'token' || event.key === null) && !current()) close() }
function visibilityChanged() { if (!current() || (expiresAt && Date.now() >= expiresAt)) close() }
window.addEventListener('storage', storageChanged)
document.addEventListener('visibilitychange', visibilityChanged)
window.addEventListener('pagehide', close)
window.addEventListener('admincore:session-cleared', close)
onBeforeRouteLeave(() => { close(); return true })
onBeforeUnmount(() => { alive = false; clear(); window.removeEventListener('storage', storageChanged); document.removeEventListener('visibilitychange', visibilityChanged); window.removeEventListener('pagehide', close); window.removeEventListener('admincore:session-cleared', close) })
</script>

<style scoped>
.sensitive-values { display: grid; gap: var(--spacing-sm); overflow-wrap: anywhere; }
.sensitive-values dt { font-weight: var(--font-weight-semibold); }
.sensitive-values dd { margin: 0 0 var(--spacing-md); }
@media print { [data-sensitive-values] { display: none !important; } }
</style>
