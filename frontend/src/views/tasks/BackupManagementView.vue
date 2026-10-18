<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="header"><h2>{{ uiText('备份与恢复') }}</h2><div class="actions"><router-link v-if="auth.can('schedule:read')" to="/tasks/schedules">{{ uiText('备份计划与手动备份') }}</router-link><BaseButton :loading="loading" :disabled="busy" @click="load">{{ uiText('刷新') }}</BaseButton></div></div></template>
      <el-alert :title="uiText('恢复会回退数据库和文件，并暂停业务写入。请先完成预检并确认业务窗口；恢复后的最终结果以宿主回执和业务核对为准。')" type="warning" :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" class="gap" />
      <el-descriptions v-if="data" :column="isMobile ? 1 : 2" border class="gap">
        <el-descriptions-item :label="uiText('功能开关')">{{ data.enabled ? uiText('已启用') : uiText('已关闭') }}</el-descriptions-item>
        <el-descriptions-item :label="uiText('执行器状态')">{{ stateLabel(data.state) }}<span v-if="data.stage"> · {{ data.stage }}</span></el-descriptions-item>
        <el-descriptions-item :label="uiText('备份目录')">{{ data.directory_label || '—' }}</el-descriptions-item>
        <el-descriptions-item :label="uiText('最近心跳')">{{ data.last_seen_at || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-empty v-if="!loading && data && !data.artifacts.length" :description="uiText('暂无已校验备份')" />
      <el-table v-if="data?.artifacts.length" :data="data.artifacts" class="gap" stripe>
        <el-table-column prop="timestamp" :label="uiText('备份时间')" min-width="170" />
        <el-table-column prop="created_at" :label="uiText('生成时间')" min-width="190" />
        <el-table-column :label="uiText('文件')" min-width="100"><template #default="{ row }">{{ row.artifacts.length }}</template></el-table-column>
        <el-table-column :label="uiText('独立副本')" width="100"><template #default="{ row }">{{ row.remote_copy ? uiText('是') : uiText('否') }}</template></el-table-column>
        <el-table-column :label="uiText('操作')" width="150"><template #default="{ row }"><el-button link type="danger" :disabled="busy || !auth.can('backup:restore') || !data?.enabled || data.state !== 'idle'" @click="begin(row.timestamp)">{{ uiText('预检恢复') }}</el-button></template></el-table-column>
      </el-table>
      <el-alert v-if="data?.last_error" :title="uiText('执行器最近错误：{p0}', { p0: data.last_error })" type="error" :closable="false" />
      <el-table v-if="data?.restore_requests.length" :data="data.restore_requests" class="gap" :aria-label="uiText('恢复请求记录')">
        <el-table-column prop="timestamp" :label="uiText('恢复备份时间')" min-width="170" />
        <el-table-column :label="uiText('恢复状态')" min-width="110"><template #default="{ row }">{{ stateLabel(row.status) }}</template></el-table-column>
        <el-table-column prop="error" :label="uiText('结果说明')" min-width="180" />
      </el-table>
    </BaseCard>
    <el-dialog v-model="dialog" :title="uiText('恢复备份')" :width="dialogWidth" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy">
      <template v-if="!preflight">
        <p>{{ uiText('将校验备份摘要、文件清单和宿主执行器状态。') }}</p>
        <el-button type="primary" :loading="busy" @click="runPreflight">{{ uiText('运行预检') }}</el-button>
      </template>
      <template v-else>
        <el-alert :title="uiText('预检通过：{p0}，独立副本：{p1}。恢复会停写并切换数据库，恢复后旧库会保留供人工核对。', { p0: preflight.timestamp, p1: preflight.remote_copy ? uiText('已配置') : uiText('未配置') })" type="warning" :closable="false" />
        <el-form label-position="top" class="form"><el-form-item :label="uiText('当前密码')"><el-input v-model="password" :aria-label="uiText('当前密码')" type="password" show-password autocomplete="current-password" /></el-form-item><el-form-item :label="uiText('确认文本')"><el-input v-model="confirmation" :aria-label="uiText('确认文本')" :placeholder="uiText('请输入：恢复备份')" /></el-form-item></el-form>
      </template>
      <p v-if="runError" role="alert">{{ runError }}</p>
      <template #footer><el-button :disabled="busy" @click="dialog = false">{{ uiText('取消') }}</el-button><el-button v-if="preflight" type="danger" :loading="busy" :disabled="busy || !password || confirmation !== '恢复备份'" @click="submitRestore">{{ uiText('确认登记恢复') }}</el-button></template>
    </el-dialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AppLayout, BaseCard, BaseButton } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useSidebar } from '@/composables/useSidebar'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { backupMessages } from '@/i18n/backupMessages'
import { backupsApi, type BackupStatus } from '@/api/backups'

const auth = useAuthStore(), modules = useModuleStore()
registerUiMessages(backupMessages)
const { isMobile } = useSidebar()
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 24px)' : '560px')
const canRead = computed(() => modules.enabled('tasks') && auth.can('backup:read'))
const canRestore = computed(() => canRead.value && auth.can('backup:restore'))
const data = ref<BackupStatus | null>(null), loading = ref(false), busy = ref(false)
const error = ref(''), runError = ref(''), dialog = ref(false), selected = ref('')
const preflight = ref<{ preflight_id: string; timestamp: string; artifacts: unknown[]; remote_copy: boolean } | null>(null)
const password = ref(''), confirmation = ref('')
let controller = new AbortController(), alive = true
function stateLabel(state: string) { return uiText(({ idle: '空闲', pending: '等待执行', running: '执行中', error: '错误', offline: '离线', succeeded: '成功', failed: '失败', unknown: '结果待核对' } as Record<string, string>)[state] || state) }
async function load() {
  if (!canRead.value) return
  const signal = controller.signal
  loading.value = true; error.value = ''
  try { const next = await backupsApi.status(signal); if (!signal.aborted && alive) data.value = next }
  catch { if (!signal.aborted && alive) error.value = uiText('备份状态加载失败，请重试') }
  finally { if (!signal.aborted) loading.value = false }
}
function begin(timestamp: string) {
  if (!canRestore.value || busy.value || data.value?.state !== 'idle') return
  selected.value = timestamp; preflight.value = null; password.value = ''; confirmation.value = ''; runError.value = ''; dialog.value = true
}
async function runPreflight() {
  if (!canRestore.value || busy.value) return
  const signal = controller.signal
  busy.value = true; runError.value = ''
  try { const next = await backupsApi.preflight(selected.value, signal); if (!signal.aborted && alive) preflight.value = next }
  catch { if (!signal.aborted && alive) runError.value = uiText('预检失败：备份可能已变化，请刷新后重试') }
  finally { if (!signal.aborted) busy.value = false }
}
async function submitRestore() {
  if (!preflight.value || !canRestore.value || busy.value || confirmation.value !== '恢复备份' || !password.value) return
  const signal = controller.signal, currentPassword = password.value
  password.value = ''; busy.value = true; runError.value = ''
  try {
    await backupsApi.restore(selected.value, preflight.value.preflight_id, currentPassword, signal)
    if (!signal.aborted && alive) { dialog.value = false; await load() }
  } catch {
    if (!signal.aborted && alive) { preflight.value = null; runError.value = uiText('恢复登记结果未确认，请刷新核对请求记录，再决定是否重新预检') }
  } finally { if (!signal.aborted) busy.value = false }
}
watch(dialog, value => { if (!value) { password.value = ''; confirmation.value = ''; preflight.value = null } })
watch(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), canRead.value, canRestore.value]), () => {
  controller.abort(); controller = new AbortController(); data.value = null; password.value = ''; dialog.value = false; preflight.value = null; loading.value = false; busy.value = false
  if (canRead.value && alive) void load()
}, { flush: 'sync' })
onMounted(() => { void load() })
onBeforeUnmount(() => { alive = false; controller.abort(); password.value = '' })
</script>

<style scoped>
h2 { margin: 0; font-size: var(--font-size-lg); }.header, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-md); }.header { justify-content: space-between; }.gap { margin-top: var(--spacing-lg); }.form { margin-top: var(--spacing-lg); } p { overflow-wrap: anywhere; }
</style>
