<template>
  <el-dialog :model-value="open && allowed" :title="uiText('通知偏好')" width="min(620px, 94vw)" append-to-body @close="emit('close')">
    <div v-if="loading" role="status">{{ uiText('正在读取通知偏好…') }}</div>
    <div v-else-if="failed">
      <el-alert :title="uiText('通知偏好读取失败，请重试')" type="error" :closable="false" />
      <el-button @click="load">{{ uiText('重试') }}</el-button>
    </div>
    <el-form v-else-if="draft && value" label-position="top" :disabled="saving">
      <p>{{ uiText('当前租户的个人偏好') }}</p>
      <el-alert :title="uiText('必须通知的站内副本始终保留；业务订阅不会授予数据权限。')" type="info" :closable="false" />
      <el-form-item :label="uiText('事件订阅')">
        <div class="preference-events">
          <el-checkbox v-for="event in value.events.filter(item => item.required)" :key="event.code" :model-value="true" disabled>
            {{ uiText(event.label) }} · {{ uiText('必须接收') }}
          </el-checkbox>
          <el-checkbox-group v-model="draft.subscriptions">
            <el-checkbox v-for="event in value.events.filter(item => !item.required)" :key="event.code" :value="event.code">{{ uiText(event.label) }}</el-checkbox>
          </el-checkbox-group>
        </div>
      </el-form-item>
      <el-form-item :label="uiText('业务提醒方式')">
        <el-radio-group v-model="draft.business_delivery_mode" :aria-label="uiText('业务提醒方式')">
          <el-radio value="immediate">{{ uiText('立即入箱') }}</el-radio>
          <el-radio value="digest">{{ uiText('定期摘要') }}</el-radio>
        </el-radio-group>
        <p class="preference-note">{{ uiText('仅适用于显式业务提醒；必须通知和模板通知保持原投递规则。摘要展开时重新检查业务权限。') }}</p>
      </el-form-item>
      <el-form-item v-if="draft.business_delivery_mode === 'digest'" :label="uiText('摘要等待时间')">
        <el-select v-model="draft.digest_minutes" :aria-label="uiText('摘要等待时间')">
          <el-option :value="60" :label="uiText('1小时')" /><el-option :value="1440" :label="uiText('24小时')" />
        </el-select>
        <p class="preference-note">{{ uiText('每条提醒入队后等待所选时长，调度刷新时合并已到期提醒；修改偏好不改写已排队时间。') }}</p>
      </el-form-item>
      <el-form-item :label="uiText('接收渠道')">
        <el-checkbox-group v-model="draft.channels">
          <el-checkbox v-for="channel in channels" :key="channel.key" :value="channel.key">
            {{ uiText(channel.label) }}<span v-if="!value.available_channels.includes(channel.key)"> · {{ uiText('部署未启用') }}</span>
          </el-checkbox>
        </el-checkbox-group>
        <p class="preference-note">{{ uiText('个人渠道选择不会启用服务器上关闭的邮件、短信或 Webhook。') }}</p>
      </el-form-item>
      <el-form-item :label="uiText('站外免打扰')">
        <el-switch v-model="draft.quiet_enabled" :active-text="uiText('开启免打扰')" />
      </el-form-item>
      <div class="preference-times">
        <el-form-item :label="uiText('开始时间')">
          <el-time-select v-model="draft.quiet_start" start="00:00" step="00:15" end="23:45" :clearable="false" :aria-label="uiText('开始时间')" />
        </el-form-item>
        <el-form-item :label="uiText('结束时间')">
          <el-time-select v-model="draft.quiet_end" start="00:00" step="00:15" end="23:45" :clearable="false" :aria-label="uiText('结束时间')" />
        </el-form-item>
      </div>
      <el-form-item :label="uiText('时区')">
        <el-input v-model="draft.timezone" maxlength="64" :aria-label="uiText('时区')" placeholder="Asia/Shanghai" />
      </el-form-item>
      <p class="preference-note">{{ uiText('支持跨午夜。免打扰只延后站外模板投递，站内收件箱不延后；超过原投递有效期的消息终止。认证验证码不受此设置影响。') }}</p>
      <el-alert v-if="saveFailed" :title="uiText('保存未确认，输入已保留；若其他窗口已修改，请重新读取后再保存。')" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="emit('close')">{{ uiText('关闭') }}</el-button>
      <el-button v-if="saveFailed" :disabled="saving" @click="load">{{ uiText('重新读取') }}</el-button>
      <el-button v-if="draft" type="primary" :disabled="loading || saving || !valid" :loading="saving" @click="save">{{ uiText('保存') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './preferenceMessages'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { uiText } from '@/i18n/uiText'
import { getNotificationPreferences, saveNotificationPreferences, type NotificationChannel, type NotificationPreferences, type NotificationPreferenceWrite } from '@/api/notificationPreferences'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useTenantStore } from '@/stores/tenants'

const props = defineProps<{ open: boolean }>(), emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore()
const allowed = computed(() => Boolean(auth.user?.id) && !auth.user?.must_change_password && modules.enabled('notifications'))
const owner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.must_change_password, tenants.currentId, allowed.value]))
const value = ref<NotificationPreferences | null>(null), draft = ref<NotificationPreferenceWrite | null>(null)
const loading = ref(false), saving = ref(false), failed = ref(false), saveFailed = ref(false)
const valid = computed(() => Boolean(draft.value?.timezone.trim()) && draft.value?.quiet_start !== draft.value?.quiet_end)
const channels: Array<{ key: NotificationChannel; label: string }> = [{ key: 'inapp', label: '站内通知' }, { key: 'email', label: '邮件' }, { key: 'webhook', label: 'Webhook' }, { key: 'sms', label: '短信' }]
let controller: AbortController | null = null, generation = 0
function reset() { generation++; controller?.abort(); value.value = null; draft.value = null; loading.value = false; saving.value = false; failed.value = false; saveFailed.value = false }
function accept(row: NotificationPreferences) {
  value.value = row
  const { revision, subscriptions, channels, quiet_enabled, quiet_start, quiet_end, timezone } = row
  draft.value = { revision, subscriptions: [...subscriptions], channels: [...channels], quiet_enabled, quiet_start, quiet_end, timezone,
    business_delivery_mode: row.business_delivery_mode || 'immediate', digest_minutes: row.digest_minutes || 60 }
}
async function load() {
  reset()
  if (!props.open || !allowed.value) return
  const tick = generation, identity = owner.value
  controller = new AbortController(); loading.value = true
  const current = () => tick === generation && identity === owner.value && props.open
  try { const row = await getNotificationPreferences(controller.signal); if (current()) accept(row) }
  catch { if (current()) failed.value = true }
  finally { if (current()) loading.value = false }
}
async function save() {
  if (!draft.value || !valid.value || saving.value || !allowed.value) return
  const tick = ++generation, identity = owner.value
  controller?.abort(); controller = new AbortController(); saving.value = true; saveFailed.value = false
  const current = () => tick === generation && identity === owner.value && props.open
  const body = { ...draft.value, subscriptions: [...draft.value.subscriptions], channels: [...draft.value.channels] }
  try { const row = await saveNotificationPreferences(body, controller.signal); if (current()) { accept(row); ElMessage.success(uiText('偏好已保存')) } }
  catch { if (current()) saveFailed.value = true }
  finally { if (current()) saving.value = false }
}
watch(() => [props.open, owner.value], (next, previous) => {
  if (previous && next[1] !== previous[1]) { reset(); if (props.open) emit('close'); return }
  void load()
}, { immediate: true })
onBeforeUnmount(reset)
</script>

<style scoped>
.preference-events { display: flex; flex-direction: column; width: 100%; }
.preference-events :deep(.el-checkbox-group) { display: flex; flex-direction: column; }
.preference-note { color: var(--el-text-color-secondary); font-size: 13px; margin: 8px 0; overflow-wrap: anywhere; }
.preference-times { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.preference-times :deep(.el-select) { width: 100%; }
@media (max-width: 480px) { .preference-times { grid-template-columns: 1fr; gap: 0; } }
</style>
