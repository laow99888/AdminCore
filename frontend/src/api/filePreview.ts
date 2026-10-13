import request from './request'
import { uiText } from '@/i18n/uiText'

export const canPreview = (type: string) => /^(pdf|jpg|jpeg|png|gif|webp|bmp|ico)$/i.test(type)

/** 与下载共用 JWT/刷新，Blob 错误体由预览窗口展示，不包含令牌 URL。 */
export async function fetchPreview(id: string, signal: AbortSignal): Promise<Blob> {
  try {
    const response = await request.get<Blob>(`/files/${id}/preview/`, { responseType: 'blob', signal })
    const blob = response.data
    if (!['image/png', 'application/pdf'].includes(blob.type) || blob.size > 10 * 1024 * 1024) {
      throw new Error(uiText('预览内容不符合安全限制，请下载查看'))
    }
    return blob
  } catch (error: any) {
    if (error.response?.data instanceof Blob && error.response.data.size < 64 * 1024) {
      try {
        const body = JSON.parse(await error.response.data.text())
        if (typeof body.message === 'string') error.message = uiText(body.message)
      } catch { /* 非 JSON 错误保留通用提示 */ }
    }
    throw error
  }
}
