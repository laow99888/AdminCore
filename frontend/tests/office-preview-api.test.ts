import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('../src/api/index', () => ({ newIdempotencyKey: () => 'office-fixture-key' }))
import request from '../src/api/request'
import { fetchOfficePreview, officePreviewConfig, isOfficeFormat } from '../src/api/officePreview'
import type { FileRow } from '../src/api'

const file = { id: 'private', lifecycle_version: 4 } as FileRow
const job = (status: string) => ({ data: { data: { id: 'j1', status, error: '', expires_at: '' } } })
describe('Office 异步私有预览', () => {
  beforeEach(() => {
    vi.useFakeTimers(); vi.clearAllMocks()
    vi.mocked(request.delete).mockResolvedValue({ data: {} })
  })
  afterEach(() => vi.useRealTimers())

  it('能力默认关闭且格式显式登记', async () => {
    vi.mocked(request.get).mockResolvedValue({ data: { data: { enabled: false } } })
    expect(await officePreviewConfig(new AbortController().signal)).toBe(false)
    for (const type of ['docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp']) expect(isOfficeFormat(type)).toBe(true)
    for (const type of ['doc', 'xls', 'ppt', 'docm', 'pdf', 'html']) expect(isOfficeFormat(type)).toBe(false)
  })

  it('提交版本与幂等键，轮询完成后仅取认证PDF字节', async () => {
    const controller = new AbortController(), blob = new Blob(['%PDF-fixture'], { type: 'application/pdf' })
    vi.mocked(request.post).mockResolvedValue(job('pending'))
    vi.mocked(request.get).mockResolvedValueOnce(job('success')).mockResolvedValueOnce({ data: blob })
    const pending = fetchOfficePreview(file, controller.signal)
    await vi.advanceTimersByTimeAsync(1500)
    expect(await pending).toBe(blob)
    expect(request.post).toHaveBeenCalledWith('/files/private/office-preview/', { lifecycle_version: 4 },
      { signal: controller.signal, headers: { 'Idempotency-Key': 'office-fixture-key' } })
    expect(request.get).toHaveBeenLastCalledWith('/files/office-preview/jobs/j1/pdf/', { responseType: 'blob', signal: controller.signal })
    expect(request.delete).not.toHaveBeenCalled()
  })

  it('关闭时停止计时与轮询，并登记取消以拒绝迟到结果', async () => {
    const controller = new AbortController()
    vi.mocked(request.post).mockResolvedValue(job('running'))
    const pending = fetchOfficePreview(file, controller.signal)
    const rejected = expect(pending).rejects.toThrow('Aborted')
    await Promise.resolve(); controller.abort(); await rejected
    await vi.advanceTimersByTimeAsync(10000)
    expect(request.get).not.toHaveBeenCalled()
    expect(request.delete).toHaveBeenCalledOnce()
  })

  it('失败状态保留可理解错误，不再轮询或取PDF', async () => {
    vi.mocked(request.post).mockResolvedValue(job('failed'))
    await expect(fetchOfficePreview(file, new AbortController().signal)).rejects.toThrow('转换失败')
    expect(request.get).not.toHaveBeenCalled()
  })

  it('拒绝HTML或超大派生内容', async () => {
    for (const blob of [new Blob([], { type: 'application/pdf' }), new Blob(['<html>'], { type: 'text/html' }),
      new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: 'application/pdf' })]) {
      vi.mocked(request.post).mockResolvedValue(job('success'))
      vi.mocked(request.get).mockResolvedValue({ data: blob })
      await expect(fetchOfficePreview(file, new AbortController().signal)).rejects.toThrow()
    }
  })
})
