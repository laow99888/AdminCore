<template>
  <AppLayout>
    <div class="file-list-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("文件列表") }}</div>
            <div class="file-header-actions">
              <DataExportButton :loading="loading || !exportReady" resource="files" />
              <PrintTableButton :title="uiText('文件列表')" :rows="tableData" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :allowed="auth.can('file:download') && modules.enabled('files')" :owner-key="printOwner" />
              <BaseButton v-if="auth.can('file:recycle')" variant="ghost" @click="router.push('/files/recycle')">{{ uiText('文件回收站') }}</BaseButton>
              <input ref="uploadInput" type="file" class="hidden-input" @change="handleUpload" />
              <BaseButton variant="primary" :loading="uploading" @click="triggerUpload">{{ uiText("上传文件") }}</BaseButton>
            </div>
          </div>
        </template>

        <BaseTable
          :data="tableData"
          :columns="tableColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :action-width="processingEnabled ? 260 : 190"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }">
            <div class="file-row-actions">
            <el-button link type="primary" size="small" :disabled="!canPreview(row.file_type) || row.size > 10 * 1024 * 1024"
              :title="uiText('支持 10 MiB 内的图片和 PDF 预览')" @click="previewFile = row">{{ uiText('预览') }}</el-button>
            <el-button link type="primary" size="small" @click="handleDownload(row)">{{ uiText("下载") }}</el-button>
            <el-button v-if="processingEnabled" link type="primary" size="small"
              :disabled="!canProcessImage(row.file_type) || row.size > 10 * 1024 * 1024" @click="processingFile = row">{{ uiText('图片处理') }}</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">{{ uiText("删除") }}</el-button>
            </div>
          </template>
        </BaseTable>
      </BaseCard>
      <FilePreviewDialog :file="previewFile" @close="previewFile = null" />
      <ImageProcessingDialog :file="processingFile" :enabled="processingEnabled" @close="processingFile = null" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { usePageState } from '@/composables/usePageState'
import { uiText } from "@/i18n/uiText"

import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable } from '@/components'
import { filesApi, downloadFile, type FileRow } from '@/api'
import FilePreviewDialog from '@/components/files/FilePreviewDialog.vue'
import { canPreview } from '@/api/filePreview'
import ImageProcessingDialog from '@/components/files/ImageProcessingDialog.vue'
import { canProcessImage, imageProcessingConfig } from '@/api/imageProcessing'
import DataExportButton from '@/components/common/DataExportButton.vue'
import PrintTableButton from '@/components/common/PrintTableButton.vue'
import type { PrintColumn } from '@/utils/printDocument'
import { useModuleStore } from '@/stores/modules'

const loading = ref(false)
const previewFile = ref<FileRow | null>(null)
const router = useRouter()
const auth = useAuthStore()
const modules = useModuleStore()
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
const printOwner = computed(() => JSON.stringify([auth.user?.id, auth.token, auth.user?.permissions, modules.config]))
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
const loadFiles = async () => {
  exportReady.value = false
  loading.value = true
  try {
    const data = await filesApi.list({ page: currentPage.value, page_size: pageSize.value })
    tableData.value = data.items
    exportReady.value = true
    total.value = data.pagination.total
  } finally {
    loading.value = false
  }
}

const triggerUpload = () => uploadInput.value?.click()

const handleUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    await filesApi.upload(file)
    ElMessage.success(uiText("上传成功"))
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
  } catch (e: any) {
    ElMessage.error(e?.message || uiText("下载失败"))
  }
}

const handleDelete = (row: FileRow) => {
  ElMessageBox.confirm(uiText("确定删除文件 {p0} 吗？", { p0: row.original_name }), uiText("提示"), { type: 'warning' })
    .then(async () => {
      await filesApi.remove(row.id)
      ElMessage.success(uiText('已移入回收站'))
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
