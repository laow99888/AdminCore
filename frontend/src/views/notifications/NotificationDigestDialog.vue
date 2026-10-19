<template>
  <el-dialog :model-value="open && allowed" :title="uiText(notificationId ? '业务通知摘要' : '通知摘要与统计')" width="min(760px, 94vw)" append-to-body @close="emit('close')">
    <template v-if="notificationId">
      <p>{{ uiText('只显示当前仍有权访问的记录；打开业务详情时仍会再次鉴权。') }}</p>
      <el-button :loading="loading" @click="load">{{ uiText('刷新权限与记录') }}</el-button>
      <el-alert v-if="failed" :title="uiText('摘要读取失败，请重试')" type="error" :closable="false" />
      <el-empty v-else-if="!loading && !references.length" :description="uiText('没有当前可访问的业务记录')" />
      <ul class="digest-links"><li v-for="item in references" :key="`${item.resource}:${item.object_id}`">
        <el-button :disabled="loading" @click="navigate(item)">{{ item.label }} · {{ uiText('查看业务记录') }}</el-button>
      </li></ul>
    </template>
    <template v-else>
      <el-alert v-if="failed" :title="uiText('摘要读取失败，请重试')" type="error" :closable="false" />
      <div v-if="status" class="digest-summary">
        <p>{{ uiText('等待摘要') }}：{{ status.pending }} · {{ uiText('已经到期') }}：{{ status.due }}</p>
        <p v-if="status.next_due_at">{{ uiText('最早到期时间') }}：{{ status.next_due_at }}</p>
      </div>
      <el-button :loading="loading" :disabled="refreshing" @click="load">{{ uiText('刷新状态') }}</el-button>
      <el-button :loading="refreshing" :disabled="loading || refreshing || !status?.due" @click="refresh">{{ uiText('合并我的到期提醒') }}</el-button>
      <p v-if="result" role="status">{{ uiText('本次入箱条目') }}：{{ result.published }} · {{ uiText('本次抑制条目') }}：{{ result.suppressed }}</p>
      <p>{{ uiText('刷新只处理已经到期的提醒，不会提前发送；已退订、撤权、失效或过期的提醒会被抑制。') }}</p>
      <section v-if="canOperate" class="notification-operations" :aria-label="uiText('通知运营统计')">
        <h3>{{ uiText('通知运营统计') }}</h3>
        <div class="operations-toolbar">
          <el-select v-model="days" :aria-label="uiText('统计时间范围')" :disabled="statsLoading"><el-option v-for="value in [1, 7, 30, 90]" :key="value" :value="value" :label="`${value} ${uiText('天')}`" /></el-select>
          <el-button :loading="statsLoading" @click="loadStats">{{ uiText('读取统计') }}</el-button>
        </div>
        <el-alert v-if="statsFailed" :title="uiText('统计读取失败，请重试')" type="error" :closable="false" />
        <template v-if="stats">
          <p>{{ uiText('当前租户，按创建时间统计') }}：{{ stats.since }} — {{ stats.until }}</p>
          <p>{{ uiText('已创建站内通知') }}：{{ stats.inbox_created }} · {{ uiText('已读站内通知') }}：{{ stats.inbox_read }} · {{ uiText('窗口内到期提醒') }}：{{ stats.due_notices }}</p>
          <el-alert :title="uiText('渠道执行完成只表示站内处理完成或外部接口接受；当前不提供供应商最终送达回执。')" type="info" :closable="false" />
          <div class="operations-table"><table><caption>{{ uiText('模板渠道执行状态') }}</caption><thead><tr><th>{{ uiText('渠道') }}</th><th>{{ uiText('状态') }}</th><th>{{ uiText('数量') }}</th></tr></thead><tbody><tr v-for="row in stats.deliveries" :key="row.channel + row.status"><td>{{ row.channel }}</td><td>{{ deliveryLabel(row.status) }}</td><td>{{ row.count }}</td></tr></tbody></table></div>
          <p v-if="!stats.deliveries.length">{{ uiText('此窗口没有渠道投递记录') }}</p>
          <dl><template v-for="row in stats.outbox" :key="row.status"><dt>{{ uiText('通知事件队列') }} · {{ queueLabel(row.status) }}</dt><dd>{{ row.count }}</dd></template></dl>
          <dl><template v-for="row in stats.business_notices" :key="row.state"><dt>{{ uiText('业务提醒') }} · {{ noticeLabel(row.state) }}</dt><dd>{{ row.count }}</dd></template></dl>
        </template>
      </section>
    </template>
    <template #footer><el-button @click="emit('close')">{{ uiText('关闭') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import './digestMessages'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { notificationDigestsApi, type DigestReference, type DigestRefresh, type DigestStatus, type NotificationOperations } from '@/api/notificationDigests'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useTenantStore } from '@/stores/tenants'
import { sessionIdentity } from '@/auth/sessionIdentity'
import { canAccessPage } from '@/router/access'
import { uiText } from '@/i18n/uiText'

const props = defineProps<{ open: boolean; notificationId?: string }>(), emit = defineEmits<{ close: []; refreshed: [] }>()
const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore(), router = useRouter()
const allowed = computed(() => Boolean(auth.user?.id) && !auth.user?.must_change_password && modules.enabled('notifications'))
const canOperate = computed(() => allowed.value && Boolean(auth.user?.is_staff || auth.user?.is_superuser) && auth.can('template:read'))
const owner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, auth.user?.must_change_password, tenants.currentId, modules.config, allowed.value]))
const loading = ref(false), refreshing = ref(false), failed = ref(false), statsLoading = ref(false), statsFailed = ref(false), days = ref(7)
const status = ref<DigestStatus>(), references = ref<DigestReference[]>([]), result = ref<DigestRefresh>(), stats = ref<NotificationOperations>()
let generation = 0, controller: AbortController | undefined, statsController: AbortController | undefined, statsGeneration = 0
function reset() { generation++; statsGeneration++; controller?.abort(); statsController?.abort(); status.value = undefined; references.value = []; result.value = undefined; stats.value = undefined; loading.value = false; refreshing.value = false; failed.value = false; statsLoading.value = false; statsFailed.value = false }
async function load() {
  if (refreshing.value) return
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); references.value = []; failed.value = false; loading.value = true
  const current = () => tick === generation && identity === owner.value && props.open && allowed.value
  try {
    if (props.notificationId) { const data = await notificationDigestsApi.detail(props.notificationId, controller.signal); if (current()) references.value = data.items }
    else { const data = await notificationDigestsApi.status(controller.signal); if (current()) status.value = data }
  } catch { if (current()) failed.value = true }
  finally { if (current()) loading.value = false }
}
async function refresh() {
  if (!allowed.value || refreshing.value || !status.value?.due) return
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); refreshing.value = true; failed.value = false
  const current = () => tick === generation && identity === owner.value && props.open && allowed.value
  try {
    const data = await notificationDigestsApi.refresh(controller.signal)
    if (current()) { result.value = data; emit('refreshed'); refreshing.value = false; await load() }
  } catch { if (current()) failed.value = true }
  finally { if (current()) refreshing.value = false }
}
async function loadStats() {
  if (!canOperate.value || props.notificationId) return
  const tick = ++statsGeneration, identity = owner.value
  statsController?.abort(); statsController = new AbortController(); statsLoading.value = true; statsFailed.value = false; stats.value = undefined
  const current = () => tick === statsGeneration && identity === owner.value && props.open && canOperate.value
  try { const data = await notificationDigestsApi.operations(days.value, statsController.signal); if (current()) stats.value = data }
  catch { if (current()) statsFailed.value = true }
  finally { if (current()) statsLoading.value = false }
}
async function navigate(item: DigestReference) {
  // 点击时重新读取，避免把对话框打开时的授权当作长期通行证。
  if (!props.notificationId || !allowed.value || loading.value) return
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); loading.value = true; failed.value = false
  try {
    const data = await notificationDigestsApi.detail(props.notificationId, controller.signal)
    if (tick !== generation || identity !== owner.value || !props.open) return
    references.value = data.items
    const target = data.items.find(row => row.resource === item.resource && row.object_id === item.object_id)
    if (!target || !target.path.startsWith('/') || target.path.startsWith('//') || !/^[0-9a-f-]{36}$/i.test(target.object_id)
        || !modules.pathEnabled(target.path) || !auth.user || !canAccessPage(target.path, auth.user, modules.pagePermissions)
        || !router.resolve(target.path).matched.some(route => route.meta.requiresAuth === true)) return
    emit('close'); void router.push({ path: target.path, query: { record: target.object_id } })
  } catch { if (tick === generation && identity === owner.value) { references.value = []; failed.value = true } }
  finally { if (tick === generation && identity === owner.value) loading.value = false }
}
const deliveryLabel = (value: string) => uiText(({ pending: '待发送', sending: '发送中', succeeded: '渠道执行完成', failed: '失败', terminated: '已终止' } as Record<string, string>)[value] || value)
const queueLabel = (value: string) => uiText(({ pending: '待派发', processing: '派发中', succeeded: '事件处理完成', failed: '失败' } as Record<string, string>)[value] || value)
const noticeLabel = (value: string) => uiText(({ pending: '等待摘要', published: '已入箱', suppressed: '已抑制' } as Record<string, string>)[value] || value)
watch(() => [props.open, props.notificationId, owner.value], (next, previous) => {
  reset()
  if (previous && next[2] !== previous[2]) { if (props.open) emit('close'); return }
  if (props.open && allowed.value) void load()
}, { immediate: true })
watch(days, () => { statsGeneration++; statsController?.abort(); stats.value = undefined; statsFailed.value = false; statsLoading.value = false })
onBeforeUnmount(reset)
</script>

<style scoped>
.digest-links { padding: 0; list-style: none; display: grid; gap: 8px; }
.digest-links .el-button { max-width: 100%; height: auto; white-space: normal; overflow-wrap: anywhere; text-align: start; }
.notification-operations { margin-top: 24px; border-top: 1px solid var(--el-border-color); padding-top: 12px; }
.operations-toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
.operations-toolbar .el-select { width: 150px; }
p { overflow-wrap: anywhere; }
.operations-table { overflow-x: auto; margin-top: 12px; }
table { width: 100%; border-collapse: collapse; }
caption { text-align: start; font-weight: 600; padding-bottom: 8px; }
th, td { text-align: start; padding: 8px; border-bottom: 1px solid var(--el-border-color); }
dl { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 12px; }
dd { margin: 0; }
</style>
