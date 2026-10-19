<template>
  <el-dialog :model-value="Boolean(file) && allowed" :title="uiText('文档版本')" width="min(680px, 94vw)" append-to-body
    :close-on-click-modal="false" :before-close="close">
    <p class="version-name">{{ file?.original_name }}</p>
    <p class="version-note">{{ uiText('版本历史仅显示你有权读取的附件。回退会新增修订，原文件和业务引用保持不变。') }}</p>
    <p v-if="loading" role="status">{{ uiText('正在读取版本…') }}</p>
    <div v-else-if="failed" role="alert"><p>{{ uiText('无法读取版本，请重试') }}</p><el-button @click="load">{{ uiText('重试') }}</el-button></div>
    <template v-else-if="history">
      <el-empty v-if="!history.items.length" :description="uiText('尚无版本历史，上传新版本后开始记录。')" />
      <ol v-else class="version-list">
        <li v-for="row in history.items" :key="row.number">
          <div class="revision-details"><strong>{{ uiText('修订 {p0}', { p0: row.number }) }} · {{ row.original_name }}</strong>
            <span>{{ fileBytes(row.size) }} · {{ formatDateTime(row.created_at) }}</span>
            <span v-if="row.restored_from !== null">{{ uiText('回退自修订 {p0}', { p0: row.restored_from }) }}</span>
            <el-tag v-if="row.number === history.version" size="small">{{ uiText('当前版本') }}</el-tag>
          </div>
          <div class="revision-actions">
            <el-button v-if="auth.can('file:download')" :disabled="busy" @click="download(row)">{{ uiText('下载') }}</el-button>
            <el-button v-if="canWrite" :disabled="busy || row.file_id === history.current_file" @click="restore(row.number)">{{ uiText('设为当前版本') }}</el-button>
          </div>
        </li>
      </ol>
      <div v-if="page > 1 || history.has_more" class="version-pages">
        <el-button :disabled="busy || page === 1" @click="changePage(-1)">{{ uiText('上一页') }}</el-button>
        <span>{{ page }}</span><el-button :disabled="busy || !history.has_more" @click="changePage(1)">{{ uiText('下一页') }}</el-button>
      </div>
    </template>
    <p v-if="writeError" role="alert">{{ writeError }}</p>
    <form v-if="canWrite" class="version-upload" @submit.prevent="append">
      <label :for="inputId">{{ uiText('新版本附件') }}</label>
      <input :id="inputId" ref="fileInput" type="file" :disabled="busy || loading || failed" @change="chooseFile" />
      <p v-if="candidate" role="status">{{ uiText('附件已上传但尚未加入版本历史，可重试登记；关闭后也可在文件列表找到它。') }}</p>
      <el-button native-type="submit" type="primary" :loading="busy" :disabled="!history || loading || failed || (!selected && !candidate)">
        {{ uiText(candidate ? '重试登记已上传附件' : '上传并登记新版本') }}
      </el-button>
    </form>
    <template #footer><el-button :disabled="busy" @click="close">{{ uiText('关闭') }}</el-button></template>
  </el-dialog>
</template>
<script setup lang="ts">
import { formatDateTime } from '@/utils/dateTime'
import { sessionIdentity } from '@/auth/sessionIdentity'
import './documentMessages'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { uiText } from '@/i18n/uiText'
import { downloadFile, filesApi, type FileRow } from '@/api'
import { responseStatus } from '@/api/request'
import { fileBytes, fileDocumentsApi, type FileHistory, type FileRevision } from '@/api/fileDocuments'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
const props = defineProps<{ file: FileRow | null }>()
const emit = defineEmits<{ close: []; updated: [] }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore(), inputId = useId()
const allowed = computed(() => auth.can('file:read') && !auth.user?.must_change_password && modules.enabled('files'))
const canWrite = computed(() => allowed.value && auth.can('file:upload'))
const identity = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password, tenants.currentId, allowed.value]))
const history = ref<FileHistory | null>(null), page = ref(1), loading = ref(false), failed = ref(false), busy = ref(false)
const selected = ref<File | null>(null), candidate = ref<string | null>(null), writeError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
let generation = 0, controller: AbortController | null = null, closed = false
function close() { if (!busy.value) { closed = true; reset(); emit('close') } }
function clearSelection() { selected.value = null; candidate.value = null; if (fileInput.value) fileInput.value.value = '' }
function reset() { generation++; controller?.abort(); history.value = null; loading.value = false; failed.value = false; busy.value = false; clearSelection(); writeError.value = '' }
async function load() {
  const tick = ++generation, owner = identity.value, id = props.file?.id
  controller?.abort(); history.value = null; failed.value = false; loading.value = false
  if (!id || !allowed.value || closed) return
  controller = new AbortController(); loading.value = true
  const valid = () => tick === generation && owner === identity.value && id === props.file?.id && !closed
  try { const result = await fileDocumentsApi.history(id, page.value, controller.signal); if (valid()) history.value = result }
  catch { if (valid()) failed.value = true }
  finally { if (valid()) loading.value = false }
}
function changePage(delta: number) { page.value += delta; void load() }
function chooseFile(event: Event) { selected.value = (event.target as HTMLInputElement).files?.[0] ?? null; candidate.value = null; writeError.value = '' }
async function write(restoreNumber?: number) {
  if (!props.file || !history.value || !canWrite.value || busy.value || loading.value || failed.value || closed) return
  if (restoreNumber === undefined && !selected.value && !candidate.value) return
  const tick = generation, owner = identity.value, id = props.file.id, version = history.value.version
  const valid = () => tick === generation && owner === identity.value && id === props.file?.id && !closed
  busy.value = true; writeError.value = ''
  let uploading = false
  try {
    if (restoreNumber === undefined && !candidate.value) {
      uploading = true
      const result = await filesApi.upload(selected.value!)
      if (!valid()) return
      candidate.value = result.data.data.id; emit('updated')
      uploading = false
    }
    if (!valid()) return
    const result = await fileDocumentsApi.append(id, restoreNumber === undefined ? { version, file_id: candidate.value! } : { version, restore_number: restoreNumber })
    if (!valid()) return
    history.value = result; page.value = 1; clearSelection()
    ElMessage.success(uiText(restoreNumber === undefined ? '版本已登记' : '已追加回退修订')); emit('updated')
  } catch (error) {
    if (!valid()) return
    if (uploading) { writeError.value = uiText('附件上传失败，请检查容量或上传限制后重试。'); return }
    writeError.value = uiText(responseStatus(error) === 409 ? '版本已变更，已重新读取；请确认后重试。' : '版本操作失败，请重试')
    if (responseStatus(error) === 409) { busy.value = false; await load(); return }
  } finally { if (valid()) busy.value = false }
}
function append() { void write() }
function restore(number: number) { void write(number) }
async function download(row: FileRevision) {
  if (!allowed.value || !auth.can('file:download') || closed) return
  try { await downloadFile(filesApi.downloadUrl(row.file_id), row.original_name) } catch { /* 共享下载入口已提示错误。 */ }
}
watch(() => [props.file?.id, identity.value], (value, previous) => {
  if (previous && value[1] !== previous[1]) { closed = true; reset(); if (props.file) emit('close'); return }
  closed = false; reset(); page.value = 1; void load()
}, { immediate: true })
onBeforeUnmount(() => { closed = true; reset() })
</script>
<style scoped>
.version-name, .version-note, .revision-details { overflow-wrap: anywhere; }
.version-note { color: var(--el-text-color-secondary); font-size: 13px; }
.version-list { padding: 0; list-style: none; }
.version-list li { display: flex; justify-content: space-between; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.revision-details { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.revision-details .el-tag { align-self: flex-start; }
.revision-actions, .version-pages { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.revision-actions .el-button, .version-pages .el-button { margin-left: 0; }
.version-upload { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-top: 20px; }
.version-upload input { max-width: 100%; }
@media (max-width: 640px) { .version-list li { flex-direction: column; } .revision-actions .el-button { min-height: 44px; } }
</style>
