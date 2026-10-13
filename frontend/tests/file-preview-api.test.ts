import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/request', () => ({ default: { get: vi.fn() } }))
import request from '../src/api/request'
import { fetchPreview } from '../src/api/filePreview'

describe('私有文件预览响应边界', () => {
  beforeEach(() => { vi.mocked(request.get).mockReset() })

  it('使用认证请求实例与取消信号，返回有界的 PNG/PDF Blob', async () => {
    const controller = new AbortController()
    const image = new Blob(['fixture'], { type: 'image/png' })
    vi.mocked(request.get).mockResolvedValue({ data: image })
    expect(await fetchPreview('private', controller.signal)).toBe(image)
    expect(request.get).toHaveBeenCalledWith('/files/private/preview/', { responseType: 'blob', signal: controller.signal })
  })

  it('拒绝 HTML 及过大的二进制响应，不交给浏览器展示', async () => {
    for (const blob of [new Blob(['<script>'], { type: 'text/html' }), new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: 'application/pdf' })]) {
      vi.mocked(request.get).mockResolvedValue({ data: blob })
      await expect(fetchPreview('private', new AbortController().signal)).rejects.toThrow('预览内容不符合安全限制')
    }
  })

  it('读取 Blob 中的服务器错误原因，同时保留状态码', async () => {
    const body = new Blob(['{"message":"文件内容损坏或与扩展名不符，无法预览"}'], { type: 'application/json' })
    Object.defineProperty(body, 'text', { value: async () => '{"message":"文件内容损坏或与扩展名不符，无法预览"}' })
    vi.mocked(request.get).mockRejectedValue(Object.assign(new Error('Request failed'), { response: { status: 422, data: body } }))
    const error = await fetchPreview('private', new AbortController().signal).catch(error => ({ message: error.message, response: { status: error.response.status } }))
    if (error instanceof Blob) throw new Error('预期请求失败')
    expect(error.message).toBe('文件内容损坏或与扩展名不符，无法预览')
    expect(error.response.status).toBe(422)
  })
})
