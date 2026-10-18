<template>
  <el-dialog :model-value="open && allowed" :title="uiText('发送业务提醒')" width="min(680px, 94vw)" append-to-body @close="emit('close')">
    <p>{{ uiText('仅发送已登记业务记录的引用；每位收件人仍须具备该记录的读取权限。按个人设置立即入箱或等待摘要。') }}</p>
    <div class="notice-search"><el-input v-model="query" :aria-label="uiText('搜索业务记录')" maxlength="80" :disabled="sending" @keyup.enter="search" /><el-button :loading="searching" :disabled="sending || query.trim().length < 2" @click="search">{{ uiText('搜索') }}</el-button></div>
    <el-alert v-if="searchFailed" :title="uiText('业务搜索失败，请重试')" type="error" :closable="false" />
    <el-empty v-if="searched && !searching && !groups.length && !searchFailed" :description="uiText('没有当前可选的业务记录')" />
    <el-radio-group v-model="selected" :disabled="sending" class="notice-records" :aria-label="uiText('业务记录')">
      <template v-for="group in groups" :key="group.source"><el-radio v-for="item in group.items" :key="item.id" :value="`${group.source}:${item.id}`">{{ group.title }} · {{ item.title }}</el-radio></template>
    </el-radio-group>
    <p>{{ uiText('收件人') }}</p><PersonPicker v-model="person" purpose="message" :disabled="sending" />
    <el-alert v-if="failed" :title="uiText('发送未确认，选择已保留；重试使用同一事件标识，避免重复提醒。')" type="error" :closable="false" />
    <p v-if="result" role="status">{{ uiText('已入箱') }}：{{ result.published }} · {{ uiText('等待摘要') }}：{{ result.pending }} · {{ uiText('已抑制') }}：{{ result.suppressed }} · {{ uiText('重复事件') }}：{{ result.replayed }}</p>
    <template #footer><el-button @click="emit('close')">{{ uiText('关闭') }}</el-button><el-button type="primary" :loading="sending" :disabled="sending || !person || !selected || Boolean(result)" @click="send">{{ uiText('发送业务提醒') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import './digestMessages'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import PersonPicker from '@/components/common/PersonPicker.vue'
import type { Person } from '@/api/personnel'
import { notificationDigestsApi, type BusinessNoticeResult, type BusinessNoticeWrite, type NoticeSearchGroup } from '@/api/notificationDigests'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useTenantStore } from '@/stores/tenants'
import { sessionIdentity } from '@/auth/sessionIdentity'
import { uiText } from '@/i18n/uiText'
const props = defineProps<{ open: boolean }>(), emit = defineEmits<{ close: []; sent: [] }>()
const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore()
const allowed = computed(() => Boolean(auth.user?.id) && !auth.user?.must_change_password && Boolean(auth.user?.is_staff || auth.user?.is_superuser) && auth.can('template:send') && modules.enabled('notifications'))
const owner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password, auth.user?.is_staff, auth.user?.is_superuser, tenants.currentId, modules.config, allowed.value]))
const query = ref(''), selected = ref(''), person = ref<Person | null>(null), groups = ref<NoticeSearchGroup[]>([])
const searching = ref(false), sending = ref(false), searchFailed = ref(false), failed = ref(false), searched = ref(false), result = ref<BusinessNoticeResult>()
let generation = 0, controller: AbortController | undefined, retry: BusinessNoticeWrite | undefined
function reset() { generation++; controller?.abort(); query.value = ''; selected.value = ''; person.value = null; groups.value = []; searching.value = false; sending.value = false; searchFailed.value = false; failed.value = false; searched.value = false; result.value = undefined; retry = undefined }
async function search() {
  if (!allowed.value || sending.value || query.value.trim().length < 2) return
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); searching.value = true; searched.value = true; searchFailed.value = false; selected.value = ''; groups.value = []
  try { const data = await notificationDigestsApi.search(query.value.trim(), controller.signal); if (tick === generation && identity === owner.value && props.open) groups.value = data }
  catch { if (tick === generation && identity === owner.value) searchFailed.value = true }
  finally { if (tick === generation && identity === owner.value) searching.value = false }
}
async function send() {
  if (!allowed.value || sending.value || searching.value || !person.value || !selected.value || result.value) return
  const [resource, object_id] = selected.value.split(':')
  if (!resource || !object_id || !groups.value.some(group => group.source === resource && group.items.some(item => item.id === object_id))) return
  const recipient_ids = [person.value.id]
  if (!retry || retry.resource !== resource || retry.object_id !== object_id || retry.recipient_ids[0] !== recipient_ids[0]) retry = { resource, object_id, recipient_ids, event_id: crypto.randomUUID() }
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); sending.value = true; failed.value = false
  try { const data = await notificationDigestsApi.send(retry, controller.signal); if (tick === generation && identity === owner.value && props.open) { result.value = data; emit('sent') } }
  catch { if (tick === generation && identity === owner.value) failed.value = true }
  finally { if (tick === generation && identity === owner.value) sending.value = false }
}
watch(() => [props.open, owner.value], (next, old) => { reset(); if (old && next[1] !== old[1] && props.open) emit('close') })
onBeforeUnmount(reset)
</script>
<style scoped>
.notice-search { display: flex; gap: 8px; }
.notice-search .el-input { min-width: 0; }
.notice-records { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin-top: 12px; max-width: 100%; }
.notice-records :deep(.el-radio) { max-width: 100%; height: auto; margin-right: 0; }
.notice-records :deep(.el-radio__label), p { white-space: normal; overflow-wrap: anywhere; }
</style>
