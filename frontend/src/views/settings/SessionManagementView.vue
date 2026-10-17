<template>
  <AppLayout>
    <div class="sessions-page">
      <div class="page-heading">
        <div><h1>{{ uiText(admin ? '在线用户' : '会话与设备') }}</h1><p>{{ uiText('列表展示近期使用过的有效 API 会话，不代表实时在线；设备信息仅作提示。') }}</p></div>
        <BaseButton size="large" variant="ghost" :loading="loading" :disabled="busy || loading" @click="load">{{ uiText('刷新') }}</BaseButton>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon role="status" />
      <form v-if="admin" class="search-form" @submit.prevent="searchUsers">
        <el-input v-model="search" :aria-label="uiText('搜索用户名')" :placeholder="uiText('搜索用户名')" maxlength="150" clearable :disabled="busy || loading" />
        <BaseButton size="large" :disabled="busy || loading" native-type="submit">{{ uiText('搜索') }}</BaseButton>
      </form>
      <p v-if="loading" role="status">{{ uiText('正在加载有效会话') }}</p>
      <BaseTable :key="admin ? 'users' : 'sessions'" :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-index="false" :show-actions="!admin || canRevoke" :action-width="admin ? 180 : 130" @update:current-page="changePage" @update:page-size="changeSize">
        <template #actions="{ row }">
          <BaseButton size="large" variant="ghost" :disabled="busy || loading || (admin && 'is_current_user' in row && row.is_current_user)" @click="prepare(row)">{{ uiText(admin ? '全部设备下线' : '下线设备') }}</BaseButton>
        </template>
      </BaseTable>
      <p v-if="admin" class="hint">{{ uiText('全部设备下线只作用于所选用户；当前管理员不能在此下线自己。') }}</p>
      <PasswordConfirmationDialog v-model="dialog" :description="confirmation" :disabled="!target || (admin && !canRevoke)" :execute="execute" @busy="busy = $event" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseTable } from '@/components'
import PasswordConfirmationDialog from '@/components/auth/PasswordConfirmationDialog.vue'
import { sessionsApi, type DeviceSession, type OnlineUser } from '@/api/sessions'
import { useAuthStore } from '@/stores/auth'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { sessionManagementMessages } from '@/i18n/sessionManagementMessages'
registerUiMessages(sessionManagementMessages)

const props = withDefaults(defineProps<{ admin?: boolean }>(), { admin: false })
const auth = useAuthStore(), router = useRouter()
const rows = ref<(DeviceSession | OnlineUser)[]>([]), target = ref<DeviceSession | OnlineUser | null>(null)
const page = ref(1), pageSize = ref(10), total = ref(0), search = ref(''), submittedSearch = ref('')
const loading = ref(false), busy = ref(false), dialog = ref(false), error = ref(''), notice = ref('')
const canRevoke = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser) && auth.can('session:revoke'))
let controller: AbortController | undefined, alive = true
const time = (value: string) => value ? new Date(value).toLocaleString() : '—'
const columns = computed(() => props.admin ? [
  { prop: 'username', label: uiText('用户名'), width: 180 },
  { prop: 'is_current_user', label: uiText('当前用户'), width: 130, render: (value: boolean) => value ? uiText('是') : '—' },
  { prop: 'session_count', label: uiText('有效会话数'), width: 140 },
  { prop: 'last_seen_at', label: uiText('最近活动'), width: 220, render: time },
] : [
  { prop: 'is_current', label: uiText('当前会话'), width: 130, render: (value: boolean) => value ? uiText('是') : '—' },
  { prop: 'user_agent', label: uiText('设备提示'), width: 260, render: (value: string) => value || uiText('未知设备') },
  { prop: 'ip_address', label: uiText('登录 IP'), width: 160, render: (value: string) => value || '—' },
  { prop: 'created_at', label: uiText('登录时间'), width: 220, render: time },
  { prop: 'last_seen_at', label: uiText('最近活动'), width: 220, render: time },
  { prop: 'expires_at', label: uiText('最晚过期时间'), width: 220, render: time },
])
const confirmation = computed(() => {
  if (!target.value) return ''
  if (props.admin) return uiText('确认让 {p0} 的全部设备下线？', { p0: (target.value as OnlineUser).username })
  return uiText((target.value as DeviceSession).is_current ? '确认下线当前会话？完成后需要重新登录。' : '确认下线所选设备？该设备需要重新登录。')
})
async function load() {
  if (busy.value) return
  controller?.abort(); controller = new AbortController()
  const activeController = controller
  loading.value = true; error.value = ''; rows.value = []; total.value = 0
  try {
    const result = props.admin ? await sessionsApi.onlineUsers(page.value, pageSize.value, submittedSearch.value, activeController.signal) : await sessionsApi.list(page.value, pageSize.value, activeController.signal)
    if (alive && controller === activeController) {
      if (!result.items.length && page.value > 1) { page.value--; void load(); return }
      rows.value = result.items; total.value = result.pagination.total
    }
  } catch { if (alive && !activeController.signal.aborted) error.value = uiText('有效会话加载失败，请刷新重试。') }
  finally { if (alive && controller === activeController) loading.value = false }
}
function changePage(value: number) { if (!busy.value) { page.value = value; void load() } }
function changeSize(value: number) { if (!busy.value) { pageSize.value = value; page.value = 1; void load() } }
function searchUsers() { if (!busy.value && !loading.value) { submittedSearch.value = search.value.trim(); page.value = 1; void load() } }
function prepare(row: DeviceSession | OnlineUser) {
  if (busy.value || loading.value || (props.admin && (!canRevoke.value || (row as OnlineUser).is_current_user))) return
  target.value = row; notice.value = ''; dialog.value = true
}
async function execute(password: string) {
  const selected = target.value
  if (!selected || (props.admin && (!canRevoke.value || (selected as OnlineUser).is_current_user))) throw new Error('permission changed')
  if (props.admin) await sessionsApi.revokeAll(selected.id, password)
  else await sessionsApi.revoke(selected.id, password)
  if (!alive) return
  if (!props.admin && (selected as DeviceSession).is_current) { auth.clearSession(); void router.replace('/login'); return }
  notice.value = uiText('所选会话已下线。')
}
watch(dialog, value => { if (!value) { target.value = null; if (alive && auth.user) void load() } })
watch(canRevoke, value => { if (props.admin && !value && !busy.value) dialog.value = false })
watch(() => props.admin, () => { controller?.abort(); rows.value = []; page.value = 1; search.value = ''; submittedSearch.value = ''; dialog.value = false; void load() })
void load()
onBeforeUnmount(() => { alive = false; controller?.abort(); target.value = null })
</script>

<style scoped>
.sessions-page { display: grid; gap: var(--spacing-lg); min-width: 0; }
.page-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--spacing-md); }
.page-heading > div { min-width: 0; }
h1 { margin: 0 0 var(--spacing-sm); font-size: var(--font-size-xl); }
p { line-height: 1.6; overflow-wrap: anywhere; }
.page-heading p, .hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
.search-form { display: flex; gap: var(--spacing-sm); max-width: 480px; }
@media (max-width: 768px) { .page-heading { flex-wrap: wrap; } }
</style>
