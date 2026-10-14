import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import { processImage, canProcessImage, imageProcessingConfig, type ImageOptions } from '../src/api/imageProcessing'
const options: ImageOptions = { width: 320, height: 240, format: 'png', quality: 80, opacity: 60, position: 'center' }
describe('有界图片派生请求', () => {
  beforeEach(() => vi.clearAllMocks())
  it('认证实例提交版本和图片，读取能力且支持中止', async () => {
    const signal = new AbortController().signal, image = new Blob(['fixture'], { type: 'image/png' })
    vi.mocked(request.get).mockResolvedValue({ data: { data: { enabled: false } } })
    expect(await imageProcessingConfig(signal)).toEqual({ enabled: false })
    vi.mocked(request.post).mockResolvedValue({ data: image })
    const mark = new File(['fixture'], 'logo.png', { type: 'image/png' })
    expect(await processImage('private-id', 3, options, mark, signal)).toBe(image)
    const call = vi.mocked(request.post).mock.calls[0]!
    expect(call[0]).toBe('/files/private-id/transform/')
    const body = call[1] as FormData
    expect(body.get('lifecycle_version')).toBe('3'); expect(body.get('width')).toBe('320')
    expect(body.get('watermark')).toBe(mark); expect(call[2]).toEqual({ responseType: 'blob', signal })
  })
  it('拒绝不匹配、空和超大结果，所有原始可处理类型均显式登记', async () => {
    for (const blob of [new Blob(['x'], { type: 'text/html' }), new Blob(['x'], { type: 'image/jpeg' }),
      new Blob([], { type: 'image/png' }), new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: 'image/png' })]) {
      vi.mocked(request.post).mockResolvedValue({ data: blob })
      await expect(processImage('f', 1, options, null, new AbortController().signal)).rejects.toThrow('安全限制')
    }
    expect(canProcessImage('JPEG')).toBe(true); expect(canProcessImage('svg')).toBe(false); expect(canProcessImage('pdf')).toBe(false)
  })
  it('有界 JSON 错误保留原因和状态，不将错误体作为图片', async () => {
    const blob = new Blob(['fixture'], { type: 'application/json' })
    Object.defineProperty(blob, 'text', { value: async () => JSON.stringify({ message: '图片已变化' }) })
    const failure = Object.assign(new Error('request failed'), { response: { status: 409, data: blob } })
    vi.mocked(request.post).mockRejectedValue(failure)
    await expect(processImage('f', 1, options, null, new AbortController().signal)).rejects.toMatchObject({ message: '图片已变化', response: { status: 409 } })
  })
})
