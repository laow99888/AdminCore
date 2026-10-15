import request, { type ApiResponse } from './request'
import { newIdempotencyKey, type FileRow } from './index'
import { registerUiMessages, uiText } from '@/i18n/uiText'

registerUiMessages({
  'Office 预览转换失败，请重试或下载原文件': 'Office preview conversion failed. Retry or download the original file.',
  'Office 预览等待超时，请稍后重试': 'Office preview timed out. Please retry later.',
  '正在安全转换 Office 文件…': 'Converting Office file securely…',
  '支持 10 MiB 内的图片、PDF 和已启用的 Office 转换预览': 'Preview images, PDFs and enabled Office conversions up to 10 MiB.',
})

interface OfficeJob { id: string; status: string; error: string; expires_at: string }
export const isOfficeFormat = (type: string) => /^(docx|xlsx|pptx|odt|ods|odp)$/i.test(type)
export async function officePreviewConfig(signal: AbortSignal): Promise<boolean> {
  return (await request.get<ApiResponse<{ enabled: boolean }>>('/files/office-preview/config/', { signal })).data.data.enabled === true
}

function wait(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
    const timer = window.setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, 1500)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
  })
}

export async function fetchOfficePreview(file: FileRow, signal: AbortSignal): Promise<Blob> {
  let job: OfficeJob | null = null
  try {
    job = (await request.post<ApiResponse<OfficeJob>>(`/files/${file.id}/office-preview/`,
      { lifecycle_version: file.lifecycle_version }, { signal, headers: { 'Idempotency-Key': newIdempotencyKey('office-preview') } })).data.data
    for (let attempt = 0; attempt < 80; attempt++) {
      if (job.status === 'success') {
        const result = (await request.get<Blob>(`/files/office-preview/jobs/${job.id}/pdf/`, { responseType: 'blob', signal })).data
        if (result.type !== 'application/pdf' || result.size === 0 || result.size > 10 * 1024 * 1024) throw new Error()
        return result
      }
      if (!['pending', 'running'].includes(job.status)) throw new Error(uiText('Office 预览转换失败，请重试或下载原文件'))
      await wait(signal)
      job = (await request.get<ApiResponse<OfficeJob>>(`/files/office-preview/jobs/${job.id}/`, { signal })).data.data
    }
    throw new Error(uiText('Office 预览等待超时，请稍后重试'))
  } finally {
    // Close/unmount stops polling and prevents a late container result from publishing.
    if (job && ['pending', 'running'].includes(job.status)) {
      void request.delete(`/files/office-preview/jobs/${job.id}/`).catch(() => {})
    }
  }
}
