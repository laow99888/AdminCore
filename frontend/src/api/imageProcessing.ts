import request, { type ApiResponse } from './request'
import { uiText } from '@/i18n/uiText'

function responseBlob(error: unknown): Blob | null {
  if (!error || typeof error !== 'object' || !('response' in error)) return null
  const response = error.response
  if (!response || typeof response !== 'object' || !('data' in response)) return null
  const data = response.data
  return data instanceof Blob || (data && typeof data === 'object' && 'text' in data && typeof data.text === 'function') ? data as Blob : null
}

export interface ProcessingConfig { enabled: boolean; max_bytes: number; max_pixels: number; max_dimension: number; watermark_max_bytes: number; formats: string[] }
export interface ImageOptions { width: number; height: number; format: 'png' | 'jpeg' | 'webp'; quality: number; opacity: number; position: 'bottom-right' | 'center' }
export const canProcessImage = (type: string) => /^(jpg|jpeg|png|gif|webp|bmp|ico)$/i.test(type)
export const imageProcessingConfig = async (signal: AbortSignal): Promise<ProcessingConfig> =>
  (await request.get<ApiResponse<ProcessingConfig>>('/files/processing_config/', { signal })).data.data

export async function processImage(id: string, version: number, options: ImageOptions, watermark: File | null, signal: AbortSignal): Promise<Blob> {
  const form = new FormData()
  form.set('lifecycle_version', String(version))
  for (const [key, value] of Object.entries(options)) form.set(key, String(value))
  if (watermark) form.set('watermark', watermark)
  try {
    const response = await request.post<Blob>(`/files/${id}/transform/`, form, { responseType: 'blob', signal })
    const blob = response.data
    if (blob.type !== `image/${options.format}` || !blob.size || blob.size > 10 * 1024 * 1024) {
      throw new Error(uiText('图片处理结果不符合安全限制'))
    }
    return blob
  } catch (error: unknown) {
    const blob = responseBlob(error)
    if (blob && blob.size < 64 * 1024) {
      try {
        const body = JSON.parse(await blob.text())
        if (typeof body.message === 'string' && error && typeof error === 'object') {
          (error as { message?: string }).message = uiText(body.message)
        }
      } catch { /* 保留固定兜底提示 */ }
    }
    throw error
  }
}
