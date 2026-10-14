<template>
  <div v-if="allowed" class="local-export-control" :aria-busy="busy" role="group" :aria-label="uiText('本地 Excel 导出')">
    <BaseButton variant="ghost" :disabled="disabled" :loading="busy" :title="hint" @click="download">
      <FileSpreadsheet :size="16" :stroke-width="1.75" aria-hidden="true" />
      <span>{{ uiText('本地 Excel（当前页）') }}</span>
    </BaseButton>
    <BaseButton v-if="busy" variant="ghost" @click="cancel">{{ uiText('取消本地导出') }}</BaseButton>
    <span class="local-export-hint">{{ hint }}</span>
    <span v-if="errorMessage" role="alert" class="local-export-error">{{ errorMessage }}</span>
  </div>
</template>

<script setup lang="ts" generic="T">
import { computed, onDeactivated, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileSpreadsheet } from 'lucide-vue-next'
import BaseButton from './BaseButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { uiText } from '@/i18n/uiText'
import type { ExportResource } from '@/api/dataExports'
import type { PrintColumn } from '@/utils/printDocument'
import { LOCAL_EXPORT_LIMITS, LocalWorkbookError, snapshotWorkbook } from '@/utils/localWorkbook'

const props = withDefaults(defineProps<{
  resource: ExportResource
  title: string
  rows: readonly T[]
  columns: readonly PrintColumn<T>[]
  currentPage?: number
  loading?: boolean
  ownerKey?: string
}>(), { currentPage: 1, loading: false, ownerKey: '' })
const auth = useAuthStore(), modules = useModuleStore(), { locale } = useI18n()
const resourcePermission: Record<ExportResource, string> = { users: 'user:read', roles: 'role:read', files: 'file:download', logs: 'log:read' }
const allowed = computed(() => auth.isAuthenticated && !!auth.user && !auth.user.must_change_password && modules.enabled('data_io') &&
  auth.can('data_io:export') && auth.can(resourcePermission[props.resource]) && (props.resource !== 'files' || modules.enabled('files')))
const busy = ref(false), errorMessage = ref('')
const disabled = computed(() => busy.value || props.loading || !allowed.value || !props.rows.length || !props.columns.length)
const hint = computed(() => props.loading ? uiText('数据加载中，暂不能导出') : uiText('仅本地导出第 {p0} 页，共 {p1} 条记录；最多 100 行', { p0: props.currentPage, p1: props.rows.length }))
let worker: Worker | undefined, timer: ReturnType<typeof setTimeout> | undefined, generation = 0
function cancel() {
  generation++
  if (worker) { worker.onmessage = null; worker.onerror = null; worker.onmessageerror = null; worker.terminate(); worker = undefined }
  if (timer !== undefined) { clearTimeout(timer); timer = undefined }
  busy.value = false
  errorMessage.value = ''
}
function fail(reason: string) {
  cancel()
  errorMessage.value = uiText(reason === 'invalid' ? '当前页内容超出本地导出限制或含不支持的值，请缩小范围后重试' : reason === 'timeout' ? '本地导出超时，已停止处理，请重试' : '本地导出失败，请重试或使用服务端导出')
}
function download() {
  if (disabled.value) return
  cancel()
  const current = generation
  busy.value = true
  try {
    const snapshot = snapshotWorkbook({ title: props.title, rows: props.rows, columns: props.columns, currentPage: props.currentPage, locale: locale.value })
    const filename = `${props.resource}-page-${props.currentPage}.xlsx`
    worker = new Worker(new URL('../../workers/localWorkbook.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (event: MessageEvent<{ ok?: boolean; bytes?: unknown; reason?: string }>) => {
      if (current !== generation || !allowed.value || props.loading) return
      const data = event.data
      if (!data || data.ok !== true || !(data.bytes instanceof ArrayBuffer) || !data.bytes.byteLength || data.bytes.byteLength > LOCAL_EXPORT_LIMITS.bytes) { fail(data?.reason || 'failed'); return }
      let url: string | undefined
      try {
        url = URL.createObjectURL(new Blob([data.bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
        const anchor = document.createElement('a')
        anchor.href = url; anchor.download = filename
        document.body.appendChild(anchor)
        try { anchor.click() } finally { anchor.remove() }
        cancel()
      } catch { fail('failed') }
      finally { if (url) URL.revokeObjectURL(url) }
    }
    worker.onerror = event => { event.preventDefault(); if (current === generation) fail('failed') }
    worker.onmessageerror = () => { if (current === generation) fail('failed') }
    timer = setTimeout(() => { if (current === generation) fail('timeout') }, 15000)
    worker.postMessage(snapshot)
  } catch (error) { fail(error instanceof LocalWorkbookError ? 'invalid' : 'failed') }
}
watch([allowed, () => auth.token, () => auth.user?.id, () => JSON.stringify(auth.user?.permissions), () => JSON.stringify(modules.config),
  () => props.ownerKey, () => props.resource, () => props.title, () => props.rows, () => props.columns, () => props.loading, () => props.currentPage, locale], cancel, { deep: true, flush: 'sync' })
onDeactivated(cancel)
onScopeDispose(cancel)
</script>

<style scoped>
.local-export-control{display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-xs);min-width:0;max-width:100%}
.local-export-control :deep(button){min-height:44px;max-width:100%;white-space:normal}
.local-export-control :deep(button > span){display:inline-flex;align-items:center;gap:var(--spacing-xs);white-space:normal;text-align:left}
.local-export-control :deep(svg){flex-shrink:0}
.local-export-hint,.local-export-error{font-size:var(--font-size-xs);overflow-wrap:anywhere}
.local-export-hint{color:var(--color-text-secondary)}
.local-export-error{color:var(--color-danger)}
@media(max-width:768px){.local-export-control,.local-export-hint{width:100%}}
</style>
