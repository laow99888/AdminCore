<template>
  <div v-if="allowed" class="print-table-control" :aria-busy="printing || loading">
    <BaseButton variant="ghost" :disabled="disabled" :loading="printing" :title="hint" @click="printCurrentPage">
      <Printer :size="16" :stroke-width="1.75" aria-hidden="true" />
      <span>{{ uiText('打印 / 保存 PDF（当前页）') }}</span>
    </BaseButton>
    <span class="print-page-hint">{{ hint }}</span>
  </div>
</template>

<script setup lang="ts" generic="T">
import { computed, onDeactivated, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Printer } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import BaseButton from './BaseButton.vue'
import { uiText } from '@/i18n/uiText'
import { openPrintDocument, PrintDocumentError, type PrintColumn, type PrintFailure, type PrintSession } from '@/utils/printDocument'

const props = withDefaults(defineProps<{
  title: string
  rows: readonly T[]
  columns: readonly PrintColumn<T>[]
  allowed?: boolean
  loading?: boolean
  currentPage?: number
  ownerKey?: string
}>(), { allowed: false, loading: false, currentPage: 1, ownerKey: '' })
const { locale } = useI18n()
const printing = ref(false)
let session: PrintSession | undefined
const disabled = computed(() => props.loading || printing.value || !props.allowed || !props.rows.length || !props.columns.length)
const hint = computed(() => props.loading ? uiText('数据加载中，暂不能打印') : uiText('仅打印当前第 {p0} 页，共 {p1} 条记录', { p0: props.currentPage, p1: props.rows.length }))
const showError = (reason: PrintFailure) => ElMessage.warning(uiText(reason === 'blocked' ? '浏览器阻止了打印窗口，请允许弹窗后重试' : reason === 'invalid' ? '打印内容超出限制或格式不受支持，请减少当前页数据后重试' : '打印窗口打开失败，请重试'))
function closeSession() {
  session?.dispose()
  session = undefined
  printing.value = false
}
function printCurrentPage() {
  if (disabled.value) return
  printing.value = true
  try {
    session = openPrintDocument({ title: props.title, rows: props.rows, columns: props.columns, currentPage: props.currentPage, locale: locale.value === 'en-US' ? 'en-US' : 'zh-CN' }, {
      allowed: () => props.allowed && !props.loading,
      onEnd: () => { session = undefined; printing.value = false },
      onError: showError,
    })
  } catch (error) {
    printing.value = false
    showError(error instanceof PrintDocumentError ? error.reason : 'failed')
  }
}
watch([() => props.allowed, () => props.ownerKey, () => props.loading, () => props.currentPage, () => props.rows, () => props.columns, locale], closeSession, { deep: true, flush: 'sync' })
onDeactivated(closeSession)
onUnmounted(closeSession)
</script>

<style scoped>
.print-table-control{display:flex;align-items:center;gap:var(--spacing-sm);flex-wrap:wrap;max-width:100%;min-width:0}
.print-table-control :deep(button){min-height:44px;max-width:100%;white-space:normal}
.print-table-control :deep(button > span){display:inline-flex;align-items:center;gap:var(--spacing-xs);white-space:normal;text-align:left}
.print-table-control :deep(svg){flex-shrink:0}
.print-page-hint{font-size:var(--font-size-xs);color:var(--color-text-secondary);overflow-wrap:anywhere}
@media(max-width:768px){.print-table-control{width:100%}.print-page-hint{width:100%}}
</style>
