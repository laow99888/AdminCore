<template>
  <el-dialog :model-value="!!credential" :title="uiText('调用统计')" width="min(660px, 94vw)" destroy-on-close @update:model-value="(value: boolean) => { if (!value) emit('close') }">
    <p>{{ credential?.name }}</p>
    <p>{{ uiText('统计通过认证、权限和限流检查的请求，包含后续返回错误的业务请求，不代表操作成功。按UTC自然日，迁移前历史不补算。') }}</p>
    <div class="statistics-controls">
      <label for="credential-statistics-days">{{ uiText('统计天数') }}</label>
      <el-input-number id="credential-statistics-days" v-model="days" :min="1" :max="90" :disabled="loading" />
      <BaseButton variant="ghost" :disabled="loading" @click="load">{{ uiText('刷新') }}</BaseButton>
    </div>
    <p v-if="loading" role="status">{{ uiText('正在加载调用统计') }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" role="alert" />
    <template v-if="data">
      <p>{{ uiText('统计起点') }}：{{ new Date(data.statistics_started_at).toLocaleString() }}</p>
      <p>{{ uiText('累计已授权请求') }}：{{ data.accepted_requests }} · {{ uiText('所选期间请求') }}：{{ data.recent_requests }}</p>
      <p v-if="!data.daily.length">{{ uiText('所选期间暂无请求') }}</p>
      <ul v-else class="statistics-days"><li v-for="day in data.daily" :key="day.day"><time>{{ day.day }} UTC</time><span>{{ day.requests }}</span></li></ul>
    </template>
    <template #footer><BaseButton variant="ghost" @click="emit('close')">{{ uiText('关闭') }}</BaseButton></template>
  </el-dialog>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { BaseButton } from '@/components'
import { apiCredentialsApi, type APICredential, type CredentialStatistics } from '@/api/apiCredentials'
import { useAuthStore } from '@/stores/auth'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { apiCredentialMessages } from '@/i18n/apiCredentialMessages'
import { getAccessToken } from '@/auth/tokenStorage'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
registerUiMessages(apiCredentialMessages)
const props = defineProps<{ credential: APICredential | null }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), days = ref(7), data = ref<CredentialStatistics | null>(null)
const loading = ref(false), error = ref('')
let controller: AbortController | undefined
function clear() { controller?.abort(); controller = undefined; data.value = null; error.value = ''; loading.value = false }
async function load() {
  clear()
  if (!props.credential || !auth.can('api_credential:read')) return
  const active = controller = new AbortController(), id = props.credential.id, actor = auth.user?.id, startingToken = getAccessToken()
  loading.value = true
  try {
    const result = await apiCredentialsApi.statistics(id, days.value, active.signal)
    if (controller === active && !active.signal.aborted && props.credential?.id === id && auth.user?.id === actor && auth.can('api_credential:read') && tokensBelongToSameSession(startingToken, getAccessToken())) data.value = result
  } catch { if (controller === active && !active.signal.aborted) error.value = uiText('调用统计加载失败，请刷新重试。') }
  finally { if (controller === active) loading.value = false }
}
watch(() => [props.credential?.id, auth.user?.id, auth.can('api_credential:read')], () => { days.value = 7; void load() }, { immediate: true })
onBeforeUnmount(clear)
</script>
<style scoped>
.statistics-controls { display: flex; gap: var(--spacing-sm); align-items: center; flex-wrap: wrap; }
.statistics-days { list-style: none; padding: 0; max-height: 320px; overflow: auto; }
.statistics-days li { display: flex; justify-content: space-between; gap: var(--spacing-md); padding: var(--spacing-sm); border-bottom: 1px solid var(--color-border); }
p { overflow-wrap: anywhere; line-height: 1.6; }
</style>
