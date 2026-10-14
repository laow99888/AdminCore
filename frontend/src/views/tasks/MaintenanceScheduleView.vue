<template>
  <AppLayout>
    <BaseCard>
      <template #header><div class="header"><h2>{{ uiText('定时维护') }}</h2><BaseButton :loading="loading" :disabled="busy" @click="load">{{ uiText('刷新') }}</BaseButton></div></template>
      <el-alert :title="uiText('仅管理注册的维护任务。清理需先预览并确认；备份需确认执行。核心可靠事件派发保持原计划。')" type="info" :closable="false" class="notice" />
      <div v-if="error" ref="errorSummary" role="alert" tabindex="-1"><el-alert :title="error" type="error" :closable="false" class="notice" /></div>
      <el-skeleton v-if="loading" :rows="6" animated />
      <el-empty v-else-if="!rows.length && !error" :description="uiText('暂无数据')" />
      <div v-else class="schedules">
        <section v-for="row in rows" :key="row.key" class="schedule" :aria-label="uiText(row.name)">
          <div class="header"><h3>{{ uiText(row.name) }}</h3><el-tag :type="row.enabled && row.module_enabled ? 'success' : 'info'">{{ uiText(row.module_enabled ? (row.enabled ? '启用' : '禁用') : '依赖模块未启用') }}</el-tag></div>
          <p class="cron">{{ row.cron.minute }} {{ row.cron.hour }} {{ row.cron.day_of_month }} {{ row.cron.month_of_year }} {{ row.cron.day_of_week }} · {{ row.cron.timezone }}</p>
          <p>{{ uiText('重叠时跳过；最长执行 {p0} 秒。中断结果未知时不自动重放。', { p0: row.time_limit_seconds }) }}</p>
          <p>{{ uiText(row.options.dry_run ? '定时计划仅预览' : row.key === 'backup' ? '定时计划执行备份' : '定时计划执行清理') }}</p>
          <el-alert v-if="row.key === 'backup'" :title="uiText('备份会短暂停写，宿主备份执行器需要保持运行；失败记录见任务中心。默认计划关闭，配置备份目标后再启用。')" type="warning" :closable="false" />
          <el-alert v-if="row.key === 'lifecycle'" :title="uiText('历史清理默认关闭，只删除超过保留期的日志和明确登记的导入源文件；使用中或近期重试的文件保留。普通文件、旧版导入文件和未知临时目录不在范围内。保留期在系统参数中设置。')" type="warning" :closable="false" />
          <el-alert v-if="!row.supported" :title="uiText('现有计划包含不支持的定义，请由管理员修复。')" type="warning" :closable="false" />
          <div v-if="row.last_run" class="last-run"><strong>{{ uiText('最近执行') }}</strong><span>{{ row.last_run.result?.skipped ? uiText('已跳过（已有同类任务执行中）') : statusLabel(row.last_run.status) }}</span><p v-if="row.last_run.result && row.key === 'lifecycle'">{{ lifecycleSummary(row.last_run.result, row.last_run.result.dry_run === true) }}</p><pre v-else-if="row.last_run.result">{{ JSON.stringify(row.last_run.result, null, 2) }}</pre><p v-if="row.last_run.error" role="alert">{{ runFailure(row.last_run.error) }}</p></div>
          <div v-if="row.preview" class="preview"><strong>{{ uiText('我的有效预览（15 分钟）') }}</strong><p v-if="row.key === 'backup'">{{ uiText('保留 {p0} 天且至少 {p1} 份完整备份；同时超出两项条件才自动清理。', { p0: row.preview.result.retention_days, p1: row.preview.result.retention_count }) }}</p><p v-else-if="row.key === 'lifecycle'">{{ lifecycleSummary(row.preview.result, true) }}</p><p v-else>{{ uiText('符合清理条件：{p0} 项；保留 {p1} 天', { p0: row.preview.result.eligible_files ?? row.preview.result.eligible_notifications ?? 0, p1: row.preview.result.retention_days }) }}</p></div>
          <div class="actions">
            <BaseButton v-if="auth.can('schedule:update')" :disabled="busy || !row.module_enabled || !row.supported" @click="edit(row)">{{ uiText('编辑计划') }}</BaseButton>
            <BaseButton v-if="auth.can('schedule:run')" :loading="busyKey === row.key + ':preview'" :disabled="busy || !row.module_enabled || !row.supported" @click="submit(row, true)">{{ uiText('运行预览') }}</BaseButton>
            <BaseButton v-if="auth.can('schedule:run')" :variant="row.key === 'backup' ? 'primary' : 'danger'" :disabled="busy || !row.module_enabled || !row.supported || (row.requires_preview && !row.preview)" @click="beginExecution(row)">{{ uiText(row.confirmation) }}</BaseButton>
          </div>
        </section>
      </div>
      <p class="help">{{ uiText('提交后刷新查看结果。预览不删除数据或生成备份；清理实际执行重新检查保留期，预览之后新增的过期数据也可能被清理。') }}</p>
      <router-link v-if="auth.can('task:read')" to="/tasks">{{ uiText('任务中心') }}</router-link>
    </BaseCard>
    <el-dialog :model-value="!!editor" :title="uiText('编辑计划')" :width="dialogWidth" :close-on-click-modal="false" :before-close="closeEditor">
      <el-form v-if="editor" label-position="top" :disabled="busy" class="editor">
        <el-form-item :label="uiText('计划启用')"><el-switch v-model="editor.enabled" :aria-label="uiText('计划启用')" /></el-form-item>
        <div class="cron-fields"><el-form-item v-for="field in cronFields" :key="field.key" :label="uiText(field.label)"><el-input v-model="editor.cron[field.key]" :aria-label="uiText(field.label)" maxlength="64" /></el-form-item></div>
        <el-form-item :label="uiText('时区（IANA 名称）')"><el-input v-model="editor.cron.timezone" :aria-label="uiText('时区（IANA 名称）')" maxlength="64" /></el-form-item>
        <p>{{ uiText('Cron 支持数字、*、范围、列表和步长，例如 */15。星期 0 为周日。') }}</p>
        <el-form-item :label="uiText('定时计划仅预览')"><el-switch v-model="editor.options.dry_run" :aria-label="uiText('定时计划仅预览')" /></el-form-item>
        <el-form-item v-if="editor.key === 'files'" :label="uiText('每批文件数')"><el-input-number v-model="editor.options.batch_size" :min="1" :max="100" :aria-label="uiText('每批文件数')" /></el-form-item>
        <el-alert :title="uiText(editor.key === 'backup' ? '启用备份计划会按时登记备份，执行器将短暂停写。请先配置备份目标和宿主执行器。关闭计划不阻止已开始或已提交的手动任务。' : '启用实际清理会按保留期永久删除过期数据。关闭计划不阻止已开始或已提交的手动任务。')" type="warning" :closable="false" />
        <p v-if="editorError" role="alert">{{ editorError }}</p>
      </el-form>
      <template #footer><div class="actions"><el-button :disabled="busy" @click="closeEditor()">{{ uiText('取消') }}</el-button><el-button :disabled="busy" @click="reloadEditor">{{ uiText('重新载入计划') }}</el-button><el-button type="primary" :loading="busyKey === 'save'" :disabled="busy" @click="save">{{ uiText('保存') }}</el-button></div></template>
    </el-dialog>
    <el-dialog :model-value="!!execution" :title="uiText(execution?.confirmation || '执行清理')" :width="dialogWidth" :close-on-click-modal="false" :before-close="closeExecution">
      <p>{{ uiText(execution?.key === 'backup' ? '备份执行时会短暂停写，宿主备份执行器需要保持运行。失败记录见任务中心。请输入“执行备份”确认。' : '清理会永久删除符合保留期的数据，不能撤销。请输入“执行清理”确认。') }}</p>
      <el-input v-model="confirmation" :disabled="busy" :aria-label="uiText(execution?.key === 'backup' ? '备份确认文本' : '清理确认文本')" />
      <p v-if="runError" role="alert">{{ runError }}</p>
      <template #footer><el-button :disabled="busy" @click="execution = null">{{ uiText('取消') }}</el-button><el-button :type="execution?.key === 'backup' ? 'primary' : 'danger'" :loading="busy" :disabled="busy || confirmation !== execution?.confirmation" @click="execution && submit(execution, false)">{{ uiText('确认执行') }}</el-button></template>
    </el-dialog>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { ElMessage } from 'element-plus'
import { AppLayout, BaseCard, BaseButton } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useSidebar } from '@/composables/useSidebar'
import { useErrorSummary } from '@/composables/useErrorSummary'
import { maintenanceApi, type MaintenanceSchedule } from '@/api/maintenance'
import { newIdempotencyKey } from '@/api'
import { uiText } from '@/i18n/uiText'

const auth = useAuthStore()
const { isMobile } = useSidebar()
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 24px)' : '560px')
const rows = ref<MaintenanceSchedule[]>([])
const loading = ref(false)
const error = ref('')
const editorError = ref('')
const runError = ref('')
const editor = ref<MaintenanceSchedule | null>(null)
const execution = ref<MaintenanceSchedule | null>(null)
const confirmation = ref('')
const busyKey = ref('')
const busy = computed(() => !!busyKey.value)
const formGuard = useUnsavedChanges({ source: () => editor.value, active: () => !!editor.value, busy: () => busy.value, canEdit: () => auth.can('schedule:update') && !!(auth.user?.is_staff || auth.user?.is_superuser), message: () => uiText('计划有未保存内容，确定放弃吗？'), clear: () => { editor.value = null } })
const attempts = new Map<string, string>()
let alive = true
let loadGeneration = 0
useErrorSummary(error)
const cronFields = [
  { key: 'minute', label: '分钟' }, { key: 'hour', label: '小时' }, { key: 'day_of_month', label: '每月日期' },
  { key: 'month_of_year', label: '月份' }, { key: 'day_of_week', label: '星期' },
] as const
function lifecycleSummary(result: Record<string, unknown>, preview: boolean) {
  const counts = (preview ? result.eligible : result.deleted) as Record<string, number> | undefined
  return uiText(preview ? '预计清理：操作日志 {p0} 条、登录日志 {p1} 条、异常日志 {p2} 条、导入源 {p3} 个；受保护文件 {p4} 个。' : '本次清理：操作日志 {p0} 条、登录日志 {p1} 条、异常日志 {p2} 条、导入源 {p3} 个；失败 {p4} 项。', { p0: counts?.operation ?? 0, p1: counts?.login ?? 0, p2: counts?.exception ?? 0, p3: counts?.imports ?? 0, p4: preview ? result.protected_imports ?? 0 : result.failed ?? 0 }) + (result.more ? ' ' + uiText('仍有待处理数据，请重新预览后继续；每类每次最多处理 1,000 条。') : '')
}
function statusLabel(status: string) { return uiText(({ pending: '等待执行', running: '执行中', success: '成功', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status) }
function runFailure(code: string) { return uiText(({ execution_not_authorized: '执行权限或账户状态已变化，请重新登录检查', preview_expired_or_policy_changed: '预览已过期或策略已变化，请重新预览', request_expired: '请求等待超过 24 小时，请重新提交', lifecycle_partial_failure: '部分文件清理失败，原记录已保留，请检查存储后重新预览', worker_lost_result_unknown: '执行中断，结果未知；请核对记录，禁止直接重放清理' } as Record<string, string>)[code] || '维护执行失败，请查看任务记录') }
async function load() {
  const generation = ++loadGeneration
  loading.value = true; error.value = ''
  try { const data = await maintenanceApi.list(); if (alive && generation === loadGeneration) rows.value = data }
  catch { if (alive && generation === loadGeneration) { rows.value = []; error.value = uiText('维护计划加载失败，请重试') } }
  finally { if (alive && generation === loadGeneration) loading.value = false }
}
function edit(row: MaintenanceSchedule) {
  editor.value = JSON.parse(JSON.stringify(row)); formGuard.markClean(); editorError.value = ''
}
function beginExecution(row: MaintenanceSchedule) { execution.value = row; confirmation.value = ''; runError.value = '' }
const discard = formGuard.confirmDiscard
async function closeEditor(done?: () => void) { if (!busy.value && await discard()) { editor.value = null; done?.() } }
function closeExecution(done: () => void) { if (!busy.value) { execution.value = null; done() } }
async function reloadEditor() {
  if (!editor.value || busy.value || !await discard()) return
  const key = editor.value.key
  await load()
  const current = rows.value.find(row => row.key === key)
  if (current) edit(current)
}
async function save() {
  if (!editor.value || busy.value) return
  const value = JSON.parse(JSON.stringify(editor.value)) as MaintenanceSchedule
  if (Object.values(value.cron).some(field => !field.trim()) || (value.key === 'files' && (!Number.isInteger(value.options.batch_size) || value.options.batch_size! < 1 || value.options.batch_size! > 100))) {
    editorError.value = uiText('请填写合法的周期、时区和参数'); return
  }
  busyKey.value = 'save'; editorError.value = ''
  try {
    await maintenanceApi.save(value)
    if (alive) { editor.value = null; ElMessage.success(uiText('保存成功')); await load() }
  } catch (exception: any) { if (alive) editorError.value = uiText(exception?.response?.status === 409 ? '内容已被其他人修改，已保留输入，请刷新后重试' : '计划保存失败，已保留输入，请检查 Cron 和时区') }
  finally { busyKey.value = '' }
}
async function submit(row: MaintenanceSchedule, dryRun: boolean) {
  if (busy.value) return
  runError.value = ''; error.value = ''
  const signature = JSON.stringify([row.key, row.revision, row.options, dryRun, !dryRun && row.requires_preview ? row.preview?.id : ''])
  const key = attempts.get(signature) || newIdempotencyKey('maintenance')
  attempts.set(signature, key); busyKey.value = row.key + (dryRun ? ':preview' : ':run')
  try {
    await maintenanceApi.run(row, dryRun, confirmation.value, key)
    if (alive) { attempts.delete(signature); execution.value = null; ElMessage.success(uiText('已登记，刷新查看执行结果')); await load() }
  } catch { if (alive) { const message = uiText(row.key === 'backup' ? '备份登记失败，请刷新计划后重试；已登记任务的执行失败见任务中心' : '提交失败，请刷新计划或重新预览后重试'); if (dryRun) error.value = message; else runError.value = message } }
  finally { busyKey.value = '' }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { alive = false; loadGeneration += 1 })
</script>

<style scoped>
h2, h3 { margin: 0; font-size: var(--font-size-lg); }
.header, .actions { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-md); flex-wrap: wrap; }
.actions { justify-content: flex-start; }
.notice, .help { margin-bottom: var(--spacing-lg); }
.schedules { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap: var(--spacing-lg); }
.schedule { padding: var(--spacing-lg); border: 1px solid var(--color-border); border-radius: var(--radius-md); min-width: 0; }
.schedule :deep(.el-tag) { color: var(--color-text-primary); }
p, pre { overflow-wrap: anywhere; font-size: var(--font-size-sm); }
.cron { font-family: monospace; }
pre { white-space: pre-wrap; max-height: 180px; overflow: auto; padding: var(--spacing-sm); background: var(--color-bg-elevated); }
.last-run, .preview { margin-block: var(--spacing-lg); }
.last-run span { margin-left: var(--spacing-sm); }
.cron-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-md); }
.help { color: var(--color-text-secondary); }
@media (max-width: 600px) { .cron-fields { grid-template-columns: 1fr; } .actions :deep(button) { min-height: 44px; } }
</style>
