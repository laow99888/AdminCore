<template>
  <el-dialog :model-value="Boolean(file) && allowed" :title="uiText('引用保护')" width="min(520px, 94vw)" append-to-body @close="emit('close')">
    <p class="reference-name">{{ file?.original_name }}</p>
    <div v-if="loading" role="status">{{ uiText('正在检查引用…') }}</div>
    <template v-else-if="failed">
      <el-alert :title="uiText('无法检查引用，请重试')" type="error" :closable="false" show-icon />
      <el-button class="reference-retry" @click="load">{{ uiText('重试') }}</el-button>
    </template>
    <el-alert v-else-if="status" :title="status.protected ? uiText('文件受引用保护') : uiText('当前未发现受保护引用')"
      :description="status.protected ? uiText('业务记录或历史快照仍在引用此文件，不能移入回收站或彻底删除。请在来源业务中处理引用；审批历史保留期间持续保护。') : uiText('此结果仅反映当前状态，删除时服务端会再次检查。')"
      :type="status.protected ? 'warning' : 'info'" :closable="false" show-icon />
    <p class="reference-note">{{ uiText('引用不授予附件访问权限，也不会显示无权查看的业务信息。') }}</p>
    <template #footer><el-button @click="emit('close')">{{ uiText('关闭') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './referenceMessages'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { uiText } from '@/i18n/uiText'
import type { FileRow } from '@/api'
import { fileReferenceStatus, type FileReferenceStatus } from '@/api/fileReferences'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'

const props = defineProps<{ file: FileRow | null }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const allowed = computed(() => auth.can('file:read') && !auth.user?.must_change_password && modules.enabled('files'))
const owner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password, tenants.currentId, allowed.value]))
const status = ref<FileReferenceStatus | null>(null), loading = ref(false), failed = ref(false)
let controller: AbortController | null = null, generation = 0
async function load() {
  const tick = ++generation, identifier = props.file?.id, identity = owner.value
  controller?.abort(); status.value = null; failed.value = false; loading.value = false
  if (!identifier || !allowed.value) return
  controller = new AbortController(); loading.value = true
  const valid = () => tick === generation && identity === owner.value && identifier === props.file?.id
  try { const result = await fileReferenceStatus(identifier, controller.signal); if (valid()) status.value = result }
  catch { if (valid()) failed.value = true }
  finally { if (valid()) loading.value = false }
}
watch(() => [props.file?.id, owner.value], (value, previous) => {
  if (previous && value[1] !== previous[1]) {
    generation++; controller?.abort(); status.value = null; loading.value = false; failed.value = false
    if (props.file) emit('close')
    return
  }
  void load()
}, { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>

<style scoped>
.reference-name { overflow-wrap: anywhere; margin: 0 0 16px; }
.reference-note { margin: 16px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.reference-retry { margin-top: 12px; }
</style>
