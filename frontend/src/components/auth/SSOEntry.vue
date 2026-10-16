<template>
  <div v-if="enabled || error" class="sso-entry">
    <el-button v-if="enabled" plain :disabled="disabled" @click="router.push('/enterprise-login')">{{ label || uiText('企业身份登录') }}</el-button>
    <template v-else><span role="status">{{ uiText('企业登录配置加载失败，本地登录仍可使用。') }}</span><el-button link :disabled="disabled || loading" @click="load">{{ uiText('重试企业登录配置') }}</el-button></template>
  </div>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ssoApi } from '@/api/sso'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { ssoMessages } from '@/i18n/ssoMessages'
registerUiMessages(ssoMessages)
defineProps<{ disabled?: boolean }>()
const router = useRouter(), enabled = ref(false), error = ref(false), loading = ref(false), label = ref('')
function responseStatus(failure: unknown): number | undefined {
  if (!failure || typeof failure !== 'object' || !('response' in failure)) return undefined
  const response: unknown = failure.response
  return response && typeof response === 'object' && 'status' in response && typeof response.status === 'number' ? response.status : undefined
}
let controller: AbortController | undefined, alive = true
async function load() {
  controller?.abort(); const active = controller = new AbortController()
  enabled.value = false; error.value = false; loading.value = true
  try { const result = await ssoApi.config(active.signal); if (alive && controller === active) { enabled.value = result.enabled; label.value = result.label || '' } }
  catch (failure: unknown) { if (alive && !active.signal.aborted && responseStatus(failure) !== 404) error.value = true }
  finally { if (alive && controller === active) loading.value = false }
}
void load()
onBeforeUnmount(() => { alive = false; controller?.abort() })
</script>
<style scoped>
.sso-entry { display: grid; gap: var(--spacing-sm); margin-top: var(--spacing-lg); font-size: var(--font-size-sm); line-height: 1.5; overflow-wrap: anywhere; }
.sso-entry .el-button { min-height: 44px; margin-left: 0; white-space: normal; }
</style>
