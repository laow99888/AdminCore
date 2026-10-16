<template>
  <BaseDialog :model-value="Boolean(file)" :title="uiText('图片处理')" width="640px" :loading="busy"
    :confirm-text="uiText('生成预览')" :confirm-disabled="!allowed || !valid" :before-close="draft.confirmDiscard"
    @confirm="generate" @update:model-value="value => { if (!value) emit('close') }">
    <p class="processing-hint">{{ uiText('保持比例且不放大；仅处理首帧，清除元数据。结果只供下载，原文件保留。') }}</p>
    <el-form label-position="top" :disabled="busy || !allowed" @submit.prevent="generate">
      <div class="processing-grid">
        <el-form-item :label="uiText('最大宽度（px）')">
          <el-input-number v-model="form.width" :min="1" :max="4096" :precision="0" :aria-label="uiText('最大宽度（px）')" />
        </el-form-item>
        <el-form-item :label="uiText('最大高度（px）')">
          <el-input-number v-model="form.height" :min="1" :max="4096" :precision="0" :aria-label="uiText('最大高度（px）')" />
        </el-form-item>
        <el-form-item :label="uiText('输出格式')">
          <el-select v-model="form.format" :aria-label="uiText('输出格式')">
            <el-option v-for="format in ['webp', 'jpeg', 'png']" :key="format" :value="format" :label="format.toUpperCase()" />
          </el-select>
        </el-form-item>
        <el-form-item :label="uiText('质量（PNG 为无损编码）')">
          <el-input-number v-model="form.quality" :min="40" :max="95" :precision="0" :disabled="form.format === 'png'" :aria-label="uiText('质量（PNG 为无损编码）')" />
        </el-form-item>
      </div>
      <el-form-item :label="uiText('水印图片（可选）')">
        <input ref="watermarkInput" type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy || !allowed"
          :aria-label="uiText('水印图片（可选）')" class="watermark-input" @change="chooseWatermark" />
        <p class="processing-hint">{{ uiText('PNG/JPEG/WebP，最大 512 KiB、1024px；可上传带中文或 Logo 的图片，水印不保存。') }}</p>
        <span v-if="watermark" class="watermark-name">{{ watermark.name }}</span>
        <el-button v-if="watermark" @click="removeWatermark">{{ uiText('移除水印') }}</el-button>
      </el-form-item>
      <div v-if="watermark" class="processing-grid">
        <el-form-item :label="uiText('不透明度（%）')">
          <el-input-number v-model="form.opacity" :min="10" :max="100" :precision="0" :aria-label="uiText('不透明度（%）')" />
        </el-form-item>
        <el-form-item :label="uiText('水印位置')">
          <el-select v-model="form.position" :aria-label="uiText('水印位置')">
            <el-option value="bottom-right" :label="uiText('右下角')" /><el-option value="center" :label="uiText('居中')" />
          </el-select>
        </el-form-item>
      </div>
    </el-form>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="busy" role="status" aria-live="polite">
      <span>{{ uiText('正在处理图片…') }}</span> <BaseButton @click="cancel">{{ uiText('取消请求') }}</BaseButton>
    </div>
    <div v-if="resultUrl" class="processing-result">
      <img :src="resultUrl" :alt="uiText('处理结果预览')" @error="failedImage" />
      <p>{{ uiText('结果大小：{p0} KiB', { p0: Math.ceil(resultSize / 1024) }) }}</p>
      <BaseButton :disabled="busy || !allowed" @click="download">{{ uiText('下载处理结果') }}</BaseButton>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import { BaseButton, BaseDialog } from '@/components'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { imageProcessingMessages } from '@/i18n/imageProcessingMessages'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { processImage, type ImageOptions } from '@/api/imageProcessing'
import { errorMessage } from '@/api/request'
import type { FileRow } from '@/api'

registerUiMessages(imageProcessingMessages)

const props = defineProps<{ file: FileRow | null; enabled: boolean }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), modules = useModuleStore()
const initial = (): ImageOptions => ({ width: 1280, height: 1280, format: 'webp', quality: 80, opacity: 60, position: 'bottom-right' })
const form = reactive<ImageOptions>(initial()), watermark = shallowRef<File | null>(null), watermarkInput = ref<HTMLInputElement>()
const watermarkRevision = ref(0), busy = ref(false), error = ref(''), resultUrl = ref(''), resultSize = ref(0)
let generation = 0, controller: AbortController | null = null
const allowed = computed(() => props.enabled && auth.isAuthenticated && !auth.user?.must_change_password &&
  auth.can('file:process') && auth.can('file:download') && modules.enabled('files'))
const valid = computed(() => [form.width, form.height].every(value => Number.isInteger(value) && value >= 1 && value <= 4096) &&
  Number.isInteger(form.quality) && form.quality >= 40 && form.quality <= 95 &&
  Number.isInteger(form.opacity) && form.opacity >= 10 && form.opacity <= 100)
function clearResult() {
  generation++; controller?.abort(); controller = null; busy.value = false
  if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
  resultUrl.value = ''; resultSize.value = 0; error.value = ''
}
function reset() {
  clearResult(); watermark.value = null; watermarkRevision.value = 0
  if (watermarkInput.value) watermarkInput.value.value = ''
  Object.assign(form, initial())
}
const draft = useUnsavedChanges({ source: () => [form, watermarkRevision.value], active: () => Boolean(props.file),
  busy: () => busy.value, canEdit: () => allowed.value, clear: reset })
function removeWatermark() {
  watermark.value = null; watermarkRevision.value++
  if (watermarkInput.value) watermarkInput.value.value = ''
}
function chooseWatermark(event: Event) {
  const input = event.target as HTMLInputElement, selected = input.files?.[0]
  input.value = ''
  if (!selected || busy.value || !allowed.value) return
  if (!selected.size || selected.size > 512 * 1024) { error.value = uiText('水印图片最大 512 KiB'); return }
  watermark.value = selected; watermarkRevision.value++
}
function cancel() { clearResult() }
function failedImage() { clearResult(); error.value = uiText('图片处理结果无法显示，请重新生成') }
async function generate() {
  const file = props.file
  if (!file || busy.value || !allowed.value || !valid.value || !draft.isCurrent()) return
  clearResult(); busy.value = true
  const current = generation
  controller = new AbortController()
  try {
    const blob = await processImage(file.id, file.lifecycle_version, { ...form }, watermark.value, controller.signal)
    if (current !== generation || props.file?.id !== file.id || !draft.isCurrent() || !allowed.value) return
    resultUrl.value = URL.createObjectURL(blob); resultSize.value = blob.size
  } catch (failure: unknown) {
    if (current === generation && !controller?.signal.aborted) error.value = errorMessage(failure, uiText('图片处理失败，请重试'))
  } finally {
    if (current === generation) { busy.value = false; controller = null }
  }
}
function download() {
  if (!resultUrl.value || !allowed.value || !draft.isCurrent() || busy.value) return
  const anchor = document.createElement('a')
  anchor.href = resultUrl.value; anchor.download = `processed.${form.format}`; anchor.click()
}
watch(() => [JSON.stringify(form), watermarkRevision.value], clearResult, { flush: 'sync' })
watch(() => props.file?.id, () => { reset(); draft.markClean() })
watch(allowed, value => { if (!value && props.file) { reset(); emit('close') } }, { flush: 'sync' })
watch(() => auth.token, (token, previous) => {
  if (props.file && !tokensBelongToSameSession(previous, token)) { reset(); emit('close') }
}, { flush: 'sync' })
onBeforeUnmount(reset)
</script>

<style scoped>
.processing-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--spacing-md); }
.processing-grid :deep(.el-input-number), .processing-grid :deep(.el-select) { width: 100%; }
.processing-hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); overflow-wrap: anywhere; }
.watermark-input { max-width: 100%; min-height: 44px; }
.watermark-name { overflow-wrap: anywhere; }
.processing-result img { display: block; max-width: 100%; max-height: 260px; object-fit: contain; }
@media (max-width: 480px) { .processing-grid { grid-template-columns: 1fr; } }
</style>
