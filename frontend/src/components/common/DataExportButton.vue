<template>
  <div v-if="allowed" class="data-export-controls" role="group" :aria-label="uiText('导出筛选结果')">
    <el-button v-for="format in formats" :key="format" :disabled="busy || loading" :loading="busyFormat === format"
      :aria-busy="busyFormat === format" :title="uiText('最多导出 5000 行、10 MiB；超限请缩小筛选范围')"
      @click="download(format)">
      <Download :size="16" aria-hidden="true" />{{ uiText('导出 {p0}', { p0: format.toUpperCase() }) }}
    </el-button>
    <span v-if="errorMessage" role="alert" class="export-error">{{ errorMessage }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onDeactivated, onScopeDispose, ref, watch } from 'vue'
import { Download } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { uiText } from '@/i18n/uiText'
import { exportData, exportErrorMessage, type ExportFilters, type ExportFormat, type ExportResource } from '@/api/dataExports'

const props = withDefaults(defineProps<{ resource: ExportResource; filters?: ExportFilters; loading?: boolean }>(), { filters: () => ({}), loading: false })
const auth = useAuthStore()
const modules = useModuleStore()
const permissions: Record<ExportResource, string> = { users: 'user:read', roles: 'role:read', logs: 'log:read', files: 'file:download' }
const allowed = computed(() => auth.isAuthenticated && !!auth.user && !auth.user.must_change_password && modules.enabled('data_io') &&
  auth.can('data_io:export') && auth.can(permissions[props.resource]) && (props.resource !== 'files' || modules.enabled('files')))
const formats: ExportFormat[] = ['csv', 'xlsx']
const busyFormat = ref<ExportFormat | null>(null)
const busy = computed(() => busyFormat.value !== null)
const errorMessage = ref('')
let generation = 0
let controller: AbortController | undefined
function cancel() {
  generation++
  controller?.abort()
  controller = undefined
  busyFormat.value = null
  errorMessage.value = ''
}
watch([allowed, () => auth.user?.id, () => auth.token, () => JSON.stringify(auth.user?.permissions), () => JSON.stringify(modules.config),
  () => props.resource, () => props.loading, () => JSON.stringify(props.filters)], cancel, { flush: 'sync' })
onDeactivated(cancel)
onScopeDispose(cancel)

async function download(format: ExportFormat) {
  if (busy.value || props.loading || !allowed.value) return
  const current = ++generation
  const resource = props.resource
  controller = new AbortController()
  busyFormat.value = format
  errorMessage.value = ''
  try {
    const blob = await exportData(resource, format, { ...props.filters }, controller.signal)
    if (current !== generation || !allowed.value) return
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    try {
      anchor.href = objectUrl
      anchor.download = `${resource}-export.${format}`
      anchor.click()
    } finally { URL.revokeObjectURL(objectUrl) }
  } catch (error) {
    if (current !== generation || controller?.signal.aborted) return
    const message = await exportErrorMessage(error)
    if (current === generation) errorMessage.value = message || uiText('导出失败，请重试')
  } finally {
    if (current === generation) { busyFormat.value = null; controller = undefined }
  }
}
</script>

<style scoped>
.data-export-controls { display: flex; align-items: center; flex-wrap: wrap; gap: var(--spacing-xs); }
.data-export-controls .el-button { min-height: 44px; margin: 0; gap: var(--spacing-xs); }
.export-error { color: var(--color-danger, #dc2626); font-size: var(--font-size-sm); max-width: 320px; overflow-wrap: anywhere; }
</style>
