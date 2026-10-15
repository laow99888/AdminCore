<template>
  <div v-if="allowed" class="import-controls" role="group" :aria-label="uiText('资源导入')">
    <el-button :disabled="!!busy || loading" :loading="busy === 'template'" @click="template">{{ uiText('导入模板') }}</el-button>
    <el-button :disabled="!!busy || loading" :loading="busy === 'import'" @click="input?.click()">{{ uiText('导入') }}</el-button>
    <input ref="input" type="file" accept=".csv,.xlsx" hidden :aria-label="uiText('选择导入文件')" @change="selected" />
    <span v-if="error" role="alert" class="import-error">{{ error }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onDeactivated, onScopeDispose, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { uiText } from '@/i18n/uiText'
import { importResource, importTemplate, type ImportResource } from '@/api/dataImports'
import { exportErrorMessage } from '@/api/dataExports'

const props = withDefaults(defineProps<{ resource: ImportResource; loading?: boolean }>(), { loading: false })
const auth = useAuthStore(), modules = useModuleStore()
const input = ref<HTMLInputElement>(), busy = ref<'' | 'import' | 'template'>(''), error = ref('')
const allowed = computed(() => auth.isAuthenticated && !!auth.user && !auth.user.must_change_password &&
  !!(auth.user.is_staff || auth.user.is_superuser) && modules.enabled('data_io') && auth.can('data_io:import') &&
  auth.can(props.resource === 'roles' ? 'role:update' : 'post:update') &&
  (props.resource !== 'posts' || modules.enabled('organization')))
let generation = 0, controller: AbortController | undefined
function cancel() {
  generation++
  controller?.abort()
  controller = undefined
  busy.value = ''
  error.value = ''
  if (input.value) input.value.value = ''
}
watch([allowed, () => auth.user?.id, () => auth.token, () => JSON.stringify(auth.user?.permissions),
  () => JSON.stringify(modules.config), () => props.resource], cancel, { flush: 'sync' })
onDeactivated(cancel)
onScopeDispose(cancel)

async function template() {
  if (busy.value || props.loading || !allowed.value) return
  const current = ++generation, resource = props.resource
  busy.value = 'template'
  controller = new AbortController()
  error.value = ''
  try {
    const blob = await importTemplate(resource, controller.signal)
    if (current !== generation || !allowed.value) return
    const url = URL.createObjectURL(blob)
    try {
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `import-template-${resource}.xlsx`
      anchor.click()
    } finally { URL.revokeObjectURL(url) }
  } catch (reason) {
    const message = await exportErrorMessage(reason)
    if (current === generation) error.value = message || uiText('下载模板失败，请重试')
  } finally { if (current === generation) { busy.value = ''; controller = undefined } }
}

async function selected(event: Event) {
  const target = event.target as HTMLInputElement, file = target.files?.[0]
  target.value = ''
  if (!file || busy.value || props.loading || !allowed.value) return
  error.value = ''
  if (!/\.(csv|xlsx)$/i.test(file.name) || file.size === 0 || file.size > 10 * 1024 * 1024) {
    error.value = uiText('请选择不超过 10 MiB 的 CSV 或 XLSX 文件')
    return
  }
  const current = ++generation, resource = props.resource
  busy.value = 'import'
  try {
    await ElMessageBox.confirm(uiText('只新增记录，不覆盖已有记录；导入结果默认停用，不分配权限或人员。最多 5000 行，逐行提交，失败行不会撤销已成功行。'), uiText('确认导入'),
      { confirmButtonText: uiText('导入'), cancelButtonText: uiText('取消'), type: 'warning' })
    if (current !== generation || !allowed.value) return
    controller = new AbortController()
    await importResource(resource, file, controller.signal)
    if (current === generation) ElMessage.success(uiText('导入任务已提交，请稍后在任务中心查看结果'))
  } catch (reason) {
    if (reason !== 'cancel' && reason !== 'close') {
      const message = await exportErrorMessage(reason)
      if (current === generation) error.value = message || uiText('导入失败，请重试')
    }
  } finally { if (current === generation) { busy.value = ''; controller = undefined } }
}
</script>

<style scoped>
.import-controls { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-xs); }
.import-controls .el-button { min-height: 44px; margin: 0; }
.import-error { color: var(--color-danger); max-width: 320px; overflow-wrap: anywhere; }
</style>
