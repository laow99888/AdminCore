<template>
  <AppLayout>
    <div class="file-list-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("文件列表") }}</div>
            <div class="file-header-actions">
              <DataExportButton :loading="loading || !exportReady" resource="files" />
              <LocalExportButton resource="files" :title="uiText('文件列表')" :rows="tableData" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :owner-key="printOwner" />
              <PrintTableButton :title="uiText('文件列表')" :rows="tableData" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :allowed="auth.can('file:download') && modules.enabled('files')" :owner-key="printOwner" />
              <BaseButton v-if="auth.can('file:recycle')" variant="ghost" @click="router.push('/files/recycle')">{{ uiText('文件回收站') }}</BaseButton>
              <input ref="uploadInput" type="file" class="hidden-input" @change="handleUpload" />
              <BaseButton variant="primary" :loading="uploading" @click="triggerUpload">{{ uiText("上传文件") }}</BaseButton>
            </div>
          </div>
        </template>

        <FileCapacityPanel :refresh-key="capacityRefresh" />
        <FileLibraryToolbar :file="organizingFile" @close="organizingFile = null" @filter="filterFiles" @updated="loadFiles" />
        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :action-width="processingEnabled ? 410 : 340"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <div class="file-row-actions">
            <el-button link type="primary" size="small" @click="organizingFile = row">{{ uiText('整理文件') }}</el-button>
            <el-button v-if="auth.can('file:read')" link type="primary" size="small" @click="referenceFile = row">{{ uiText('引用保护') }}</el-button>
            <el-button v-if="auth.can('file:read')" link type="primary" size="small" @click="versionFile = row">{{ uiText('文档版本') }}</el-button>
            <el-button link type="primary" size="small" :disabled="!(canPreview(row.file_type) || (officeAvailable && isOfficeFormat(row.file_type))) || row.size > 10 * 1024 * 1024"
              :title="uiText('支持 10 MiB 内的图片、PDF 和已启用的 Office 转换预览')" @click="previewFile = row">{{ uiText('预览') }}</el-button>
            <el-button link type="primary" size="small" @click="handleDownload(row)">{{ uiText("下载") }}</el-button>
            <el-button v-if="processingEnabled" link type="primary" size="small"
              :disabled="!canProcessImage(row.file_type) || row.size > 10 * 1024 * 1024" @click="processingFile = row">{{ uiText('图片处理') }}</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
            </div>
          </template>
        </BaseTable>
      </BaseCard>
      <FilePreviewDialog :file="previewFile" @close="previewFile = null" />
      <FileReferencesDialog :file="referenceFile" @close="referenceFile = null" />
      <FileVersionsDialog :file="versionFile" @close="versionFile = null" @updated="filesUpdated" />
      <ImageProcessingDialog :file="processingFile" :enabled="processingEnabled" @close="processingFile = null" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import { useLatestRead } from '@/composables/useLatestRead'
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable } from '@/components'
import { filesApi, downloadFile, type FileRow } from '@/api'
import { notifyError, responseStatus } from '@/api/request'
import FilePreviewDialog from '@/components/files/FilePreviewDialog.vue'
import FileReferencesDialog from '@/components/files/FileReferencesDialog.vue'
import FileVersionsDialog from '@/components/files/FileVersionsDialog.vue'
import FileCapacityPanel from '@/components/files/FileCapacityPanel.vue'
import { canPreview } from '@/api/filePreview'
import { isOfficeFormat, officePreviewConfig } from '@/api/officePreview'
import ImageProcessingDialog from '@/components/files/ImageProcessingDialog.vue'
import { canProcessImage, imageProcessingConfig } from '@/api/imageProcessing'
import DataExportButton from '@/components/common/DataExportButton.vue'
import PrintTableButton from '@/components/common/PrintTableButton.vue'
import LocalExportButton from '@/components/common/LocalExportButton.vue'
import type { PrintColumn } from '@/utils/printDocument'
import { useModuleStore } from '@/stores/modules'
import FileLibraryToolbar from '@/components/files/FileLibraryToolbar.vue'
import type { FileLibraryFilter } from '@/api/fileLibrary'

const loading = ref(false)
const organizingFile = ref<FileRow | null>(null)
const libraryFilter = ref<FileLibraryFilter>({ folder: '', tag: '', search: '' })
const previewFile = ref<FileRow | null>(null)
const referenceFile = ref<FileRow | null>(null)
const versionFile = ref<FileRow | null>(null), capacityRefresh = ref(0)
const router = useRouter()
const auth = useAuthStore()
const modules = useModuleStore()
const officeAvailable = ref(false)
let officeController: AbortController | null = null, officeGeneration = 0
watch(() => JSON.stringify([auth.user?.id, auth.can('file:download'), modules.enabled('files')]), async () => {
  const current = ++officeGeneration
  officeController?.abort(); officeAvailable.value = false; previewFile.value = null
  if (!auth.can('file:download') || !modules.enabled('files')) return
  officeController = new AbortController()
  try {
    const enabled = await officePreviewConfig(officeController.signal)
    if (current === officeGeneration) officeAvailable.value = enabled
  } catch { /* 配置读取失败保持转换入口关闭。 */ }
}, { immediate: true })
onBeforeUnmount(() => { officeGeneration++; officeController?.abort() })
const processingFile = ref<FileRow | null>(null), processingAvailable = ref(false)
const processingAllowed = computed(() => auth.can('file:process') && auth.can('file:download') && modules.enabled('files'))
const processingEnabled = computed(() => processingAllowed.value && processingAvailable.value)
let processingController: AbortController | null = null, processingGeneration = 0
watch(() => JSON.stringify([auth.user?.id, processingAllowed.value]), async () => {
  const current = ++processingGeneration
  processingController?.abort(); processingAvailable.value = false; processingFile.value = null
  if (!processingAllowed.value) return
  processingController = new AbortController()
  try {
    const config = await imageProcessingConfig(processingController.signal)
    if (current === processingGeneration) processingAvailable.value = config.enabled === true
  } catch { /* 能力配置读取失败时撤下入口；原文件操作仍可用。 */ }
}, { immediate: true })
onBeforeUnmount(() => { processingGeneration++; processingController?.abort() })
const printOwner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, modules.config]))
const printColumns = computed<PrintColumn<FileRow>[]>(() => [
  { label: uiText('文件名'), value: row => row.original_name },
  { label: uiText('类型'), value: row => row.file_type },
  { label: uiText('大小'), value: row => row.size_display },
  { label: uiText('上传者'), value: row => row.uploader_name },
])
const uploading = ref(false)
const uploadInput = ref<HTMLInputElement>()
const tableData = ref<FileRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

usePageState({ currentPage, pageSize })
const tableColumns = [
  { prop: 'original_name', label: uiText("文件名") },
  { prop: 'file_type', label: uiText("类型"), width: '90px' },
  { prop: 'size_display', label: uiText("大小"), width: '100px' },
  { prop: 'uploader_name', label: uiText("上传者"), width: '120px' },
  { prop: 'download_count', label: uiText("下载次数"), width: '100px' },
  { prop: 'created_at', label: uiText("上传时间"), width: '180px' },
]

const exportReady = ref(false)
const beginRead = useLatestRead(() => { tableData.value = []; total.value = 0; exportReady.value = false; loading.value = false })
const loadFiles = async () => {
  const current = beginRead()
  exportReady.value = false
  loading.value = true
  try {
    const data = await filesApi.list({ page: currentPage.value, page_size: pageSize.value,
      folder: libraryFilter.value.folder || undefined, tag: libraryFilter.value.tag || undefined,
      search: libraryFilter.value.search || undefined })
    if (!current()) return
    const last = Math.max(1, Math.ceil(data.pagination.total / pageSize.value))
    if (currentPage.value > last) { currentPage.value = last; await loadFiles(); return }
    tableData.value = data.items
    exportReady.value = true
    total.value = data.pagination.total
  } catch (error) {
    if (current() && responseStatus(error) === 404 && currentPage.value > 1) { currentPage.value = 1; await loadFiles() }
  } finally {
    if (current()) loading.value = false
  }
}

const triggerUpload = () => uploadInput.value?.click()
function filesUpdated() { capacityRefresh.value++; void loadFiles() }
function filterFiles(filter: FileLibraryFilter) {
  libraryFilter.value = filter; currentPage.value = 1; void loadFiles()
}

const handleUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    await filesApi.upload(file)
    ElMessage.success(uiText("上传成功"))
    capacityRefresh.value++
    currentPage.value = 1
    loadFiles()
  } catch {
    // 拦截器已提示（类型白名单/大小限制）
  } finally {
    uploading.value = false
  }
}

const handleDownload = async (row: FileRow) => {
  try {
    await downloadFile(filesApi.downloadUrl(row.id), row.original_name)
  } catch (error: unknown) {
    notifyError(error, uiText("下载失败"))
  }
}

const handleDelete = (row: FileRow) => {
  ElMessageBox.confirm(uiText("确定删除文件 {p0} 吗？", { p0: row.original_name }), uiText("提示"), { type: 'warning' })
    .then(async () => {
      await filesApi.remove(row.id)
      if (tableData.value.length === 1 && currentPage.value > 1) currentPage.value--
      ElMessage.success(uiText('已移入回收站'))
      capacityRefresh.value++
      loadFiles()
    })
    .catch(() => {})
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadFiles()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadFiles()
}

loadFiles()
</script>

<style scoped>
.file-list-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.file-header-actions { display: flex; gap: var(--spacing-sm); flex-wrap: wrap; }
.file-row-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--spacing-sm); width: 100%; }
.file-row-actions .el-button { margin-left: 0; }

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.hidden-input {
  display: none;
}
</style>
