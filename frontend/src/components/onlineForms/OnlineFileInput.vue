<template>
  <div class="attachment-input">
    <el-select v-if="!formDisabled" :id="id" :aria-label="label" :model-value="modelValue || undefined"
      :disabled="!canRead || !context" filterable remote clearable :loading="loading" :remote-method="search"
      @visible-change="(value: boolean) => { if (value) search('') }" @update:model-value="emit('update:modelValue', $event || undefined)">
      <!-- 远程 select 不监听现存选项标签；授权解析或撤权后须重新登记，清除缓存名称。 -->
      <el-option v-for="item in options" :key="`${item.id}:${item.original_name}`" :value="item.id" :label="item.original_name" />
      <el-option v-if="modelValue && !options.some(item => item.id === modelValue)" :key="`${modelValue}:${selected?.original_name || ''}`" :value="String(modelValue)"
        :label="selected?.original_name || uiText('附件不可用或无权访问')" />
    </el-select>
    <span v-else-if="selected" class="filename">{{ selected.original_name }}</span>
    <span v-else-if="modelValue">{{ uiText('附件不可用或无权访问') }}</span>
    <span v-else>{{ uiText('未选择附件') }}</span>
    <div class="attachment-actions">
      <el-button v-if="!formDisabled && context && auth.can('file:upload') && canRead" :disabled="uploading" :loading="uploading" @click="input?.click()">{{ uiText('上传附件') }}</el-button>
      <input v-if="!formDisabled" ref="input" type="file" hidden :aria-label="uiText('上传附件')" @change="upload" />
      <el-button v-if="selected && auth.can('file:download') && canPreview(selected.file_type) && selected.size <= 10 * 1024 * 1024"
        :disabled="false" @click="preview = previewRow(selected)">{{ uiText('预览') }}</el-button>
      <el-button v-if="selected && auth.can('file:download')" :disabled="false" @click="download">{{ uiText('下载') }}</el-button>
      <el-button v-if="more && !formDisabled" :disabled="loading" @click="loadMore">{{ uiText('加载更多') }}</el-button>
    </div>
    <small v-if="!context">{{ uiText('保存表单后可选择附件；新增附件字段请先保存') }}</small>
    <small v-else-if="!formDisabled">{{ uiText('仅可绑定当前租户中有权读取的文件，历史附件始终引用原文件版本') }}</small>
    <p v-if="failure" role="alert">{{ failure }} <el-button :disabled="loading" link @click="retry">{{ uiText('重试') }}</el-button></p>
    <FilePreviewDialog v-if="preview" :file="preview" @close="preview = null" />
  </div>
</template>
<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './attachmentMessages'
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { useFormDisabled } from 'element-plus'
import { filesApi, downloadFile, type FileRow } from '@/api'
import { errorMessage } from '@/api/request'
import { onlineFormAttachmentsApi, type OnlineAttachment, type OnlineAttachmentContext } from '@/api/onlineFormAttachments'
import { canPreview } from '@/api/filePreview'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { uiText } from '@/i18n/uiText'

const FilePreviewDialog = defineAsyncComponent(() => import('@/components/files/FilePreviewDialog.vue'))
const props = defineProps<{ id: string; label: string; modelValue?: unknown; context?: OnlineAttachmentContext; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const auth = useAuthStore(), tenants = useTenantStore(), formDisabled = useFormDisabled()
const canRead = computed(() => auth.can('file:read'))
const options = ref<OnlineAttachment[]>([]), selected = ref<OnlineAttachment | null>(null), preview = ref<FileRow | null>(null)
const loading = ref(false), uploading = ref(false), more = ref(false), failure = ref(''), input = ref<HTMLInputElement>()
let generation = 0, controller: AbortController | undefined, page = 1, query = ''
let uploadGeneration = 0, lastRead = { resolve: false, append: false }

function previewRow(row: OnlineAttachment): FileRow {
  // 预览组件仅使用 id/type/name/size；从不构造或复制存储 URL。
  return { ...row, file: '', size_display: '', description: '', download_count: 0, created_at: '', is_deleted: false, deleted_at: null, lifecycle_version: 1 }
}
function reset() {
  uploadGeneration++
  generation++; controller?.abort(); options.value = []; selected.value = null; preview.value = null
  loading.value = false; uploading.value = false; more.value = false; failure.value = ''; page = 1; query = ''
}
async function load(resolve = false, append = false) {
  const context = props.context
  if (!context || !canRead.value || (!resolve && formDisabled.value)) return
  const current = ++generation
  lastRead = { resolve, append }
  controller?.abort(); controller = new AbortController(); loading.value = true; failure.value = ''
  try {
    const result = await onlineFormAttachmentsApi.choices(context, props.id, {
      selected: typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : undefined, q: query, page, resolve,
    }, controller.signal)
    if (current !== generation) return
    selected.value = result.selected
    if (!resolve) { options.value = append ? [...options.value, ...result.items] : result.items; more.value = result.has_more }
  } catch (err) {
    if (current === generation) { selected.value = null; failure.value = errorMessage(err, uiText('附件加载失败，请重试')); if (append) page-- }
  } finally { if (current === generation) loading.value = false }
}
function search(value: string) { query = value; page = 1; void load() }
function loadMore() { if (!loading.value) { page++; void load(false, true) } }
function retry() { if (lastRead.append) page++; void load(lastRead.resolve, lastRead.append) }
async function upload(event: Event) {
  const element = event.target as HTMLInputElement, file = element.files?.[0]
  element.value = ''
  if (!file || formDisabled.value || !props.context || !canRead.value || !auth.can('file:upload') || uploading.value) return
  const current = ++uploadGeneration
  uploading.value = true; failure.value = ''
  try {
    const result = await filesApi.upload(file)
    if (current !== uploadGeneration || formDisabled.value) return
    // 上传使用当前租户；选项解析再次按目标表单/记录与 ACL 复核，不能盲信上传返回值。
    const verified = await onlineFormAttachmentsApi.choices(props.context, props.id, { selected: result.data.data.id, resolve: true })
    if (current !== uploadGeneration || formDisabled.value) return
    if (!verified.selected) throw new Error(uiText('附件不可用或无权访问'))
    selected.value = verified.selected; emit('update:modelValue', selected.value.id)
  } catch (err) { if (current === uploadGeneration) failure.value = errorMessage(err, uiText('附件上传失败，请重试')) }
  finally { if (current === uploadGeneration) uploading.value = false }
}
async function download() {
  if (!selected.value || !auth.can('file:download')) return
  await downloadFile(filesApi.downloadUrl(selected.value.id), selected.value.original_name).catch(() => {})
}
watch(() => JSON.stringify([JSON.stringify(props.context), props.id, props.modelValue, auth.user?.id, sessionIdentity(auth.token),
  JSON.stringify(auth.user?.permissions), tenants.currentId]), () => { reset(); if (props.modelValue) void load(true) }, { immediate: true, flush: 'sync' })
watch(formDisabled, () => { reset(); if (props.modelValue) void load(true) }, { flush: 'sync' })
onBeforeUnmount(reset)
</script>
<style scoped>
.attachment-input { display: grid; gap: 6px; width: 100%; min-width: 0; }
.attachment-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.attachment-actions :deep(.el-button + .el-button) { margin-left: 0; }
.filename { overflow-wrap: anywhere; }
small { color: var(--el-text-color-secondary); line-height: 1.6; }
p { color: var(--el-color-danger); margin: 0; }
@media(max-width:768px) { .attachment-actions :deep(button) { min-height: 44px; } }
</style>
