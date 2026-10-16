<template>
  <BaseDialog :model-value="Boolean(file)" :title="uiText('预览：{p0}', { p0: file?.original_name || '' })"
    width="min(960px, calc(100vw - 48px))" :show-cancel="false" :confirm-text="uiText('关闭')"
    @update:model-value="value => { if (!value) emit('close') }" @confirm="emit('close')">
    <div class="preview-body" :aria-busy="busy" aria-live="polite">
      <p v-if="busy" role="status">{{ uiText(file && isOfficeFormat(file.file_type) ? '正在安全转换 Office 文件…' : '正在加载预览…') }}</p>
      <div v-if="error" role="alert">
        <p>{{ error }}</p>
        <BaseButton :disabled="busy" @click="load">{{ uiText('重试') }}</BaseButton>
      </div>
      <img v-if="imageUrl" :src="imageUrl" :alt="file?.original_name" class="preview-image"
        @load="busy = false" @error="imageFailed" />
      <template v-if="pdf">
        <div class="page-controls">
          <BaseButton :disabled="busy || pageNumber <= 1" @click="renderPage(pageNumber - 1)">{{ uiText('上一页') }}</BaseButton>
          <span>{{ uiText('第 {p0} / {p1} 页', { p0: pageNumber, p1: pageCount }) }}</span>
          <BaseButton :disabled="busy || pageNumber >= pageCount" @click="renderPage(pageNumber + 1)">{{ uiText('下一页') }}</BaseButton>
        </div>
        <canvas ref="canvas" class="preview-canvas" role="img" :aria-label="uiText('PDF 第 {p0} 页', { p0: pageNumber })" />
        <p class="preview-hint">{{ uiText('此处显示 PDF 页面图像，文字检索和辅助阅读请下载原文件。') }}</p>
      </template>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import { BaseDialog, BaseButton } from '@/components'
import { uiText } from '@/i18n/uiText'
import type { FileRow } from '@/api'
import { fetchPreview } from '@/api/filePreview'
import { fetchOfficePreview, isOfficeFormat } from '@/api/officePreview'
import { errorMessage } from '@/api/request'

const props = defineProps<{ file: FileRow | null }>()
const emit = defineEmits<{ close: [] }>()
const busy = ref(false), error = ref(''), imageUrl = ref('')
const pdf = shallowRef<PDFDocumentProxy | null>(null)
const pageNumber = ref(1), pageCount = ref(0), canvas = ref<HTMLCanvasElement>()
let controller: AbortController | null = null
let task: PDFDocumentLoadingTask | null = null
let render: RenderTask | null = null
let generation = 0

function clear() {
  generation++
  controller?.abort()
  controller = null
  render?.cancel()
  render = null
  // loadingTask.destroy 同时销毁文档和专属 worker，包括关闭期间尚未加载完的情况。
  void task?.destroy().catch(() => {})
  task = null
  pdf.value = null
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
  if (canvas.value) { canvas.value.width = 0; canvas.value.height = 0 }
  pageNumber.value = 1
  pageCount.value = 0
  busy.value = false
  error.value = ''
}

function imageFailed() {
  error.value = uiText('图片预览失败，请重试或下载查看')
  busy.value = false
  URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
}

async function renderPage(number: number) {
  const document = pdf.value, current = generation
  if (!document) return
  busy.value = true
  error.value = ''
  try {
    const page = await document.getPage(number)
    if (current !== generation) return
    await nextTick()
    const element = canvas.value
    if (!element) return
    const base = page.getViewport({ scale: 1 })
    // 页面宽度适配，最多 4M 像素；只保留当前页画布。
    const width = Math.min(element.parentElement?.clientWidth || 800, 900)
    const scale = Math.min(width / base.width * Math.min(window.devicePixelRatio || 1, 2), Math.sqrt(4_000_000 / (base.width * base.height)))
    const viewport = page.getViewport({ scale })
    element.width = Math.ceil(viewport.width)
    element.height = Math.ceil(viewport.height)
    render = page.render({ canvas: element, viewport, annotationMode: 0 })
    await render.promise
    if (current === generation) pageNumber.value = number
    page.cleanup()
  } catch {
    if (current === generation) error.value = uiText('PDF 页面绘制失败，请重试或下载查看')
  } finally {
    if (current === generation) { busy.value = false; render = null }
  }
}

async function load() {
  clear()
  const file = props.file, current = generation
  if (!file) return
  controller = new AbortController()
  busy.value = true
  try {
    const blob = isOfficeFormat(file.file_type)
      ? await fetchOfficePreview(file, controller.signal)
      : await fetchPreview(file.id, controller.signal)
    if (current !== generation) return
    if (blob.type === 'image/png') {
      imageUrl.value = URL.createObjectURL(blob)
      return // 图片 onload 后再结束加载状态。
    }
    // 查看文件时才下载渲染器与 worker，不进入登录页或普通列表首屏。
    const [library, worker, buffer] = await Promise.all([
      import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url'), blob.arrayBuffer(),
    ])
    if (current !== generation) return
    library.GlobalWorkerOptions.workerSrc = worker.default
    task = library.getDocument({ data: new Uint8Array(buffer), enableXfa: false,
      disableFontFace: true, useWorkerFetch: false, useWasm: false, maxImageSize: 16_000_000,
      stopAtErrors: true, cMapUrl: '/pdf-assets/cmaps/', cMapPacked: true,
      standardFontDataUrl: '/pdf-assets/standard_fonts/', wasmUrl: '/pdf-assets/wasm/' })
    const document = await task.promise
    if (current !== generation) return
    if (document.numPages > 100) throw new Error(uiText('PDF 页数超出预览限制'))
    pdf.value = document
    pageCount.value = document.numPages
    await renderPage(1)
  } catch (failure: unknown) {
    if (current === generation) { error.value = errorMessage(failure, uiText('预览加载失败，请重试或下载查看')); busy.value = false }
  }
}

watch(() => props.file, file => { if (file) void load(); else clear() }, { immediate: true })
onBeforeUnmount(clear)
</script>

<style scoped>
.preview-body { min-height: 120px; text-align: center; }
.preview-image { max-width: 100%; max-height: 50vh; object-fit: contain; }
.preview-canvas { display: block; max-width: 100%; height: auto; margin: auto; }
.page-controls { display: flex; align-items: center; justify-content: center; gap: var(--spacing-sm); flex-wrap: wrap; margin-bottom: var(--spacing-md); }
.preview-hint { color: var(--color-text-secondary); margin-top: var(--spacing-sm); }
</style>
