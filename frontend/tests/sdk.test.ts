import { beforeEach, expect, it, vi } from 'vitest'
import axios from 'axios'
const transport = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../src/api/request', () => ({ default: transport }))
import { sdk } from '../src/api/sdk'
import { backupsApi } from '../src/api/backups'

beforeEach(() => { vi.resetAllMocks(); transport.request.mockResolvedValue({ data: { code: 200, message: 'success', data: { enabled: true } } }) })

it('备份入口实际使用 SDK，保持信号及原响应信封', async () => {
  const signal = new AbortController().signal
  expect(await backupsApi.status(signal)).toEqual({ enabled: true })
  expect(transport.request).toHaveBeenCalledWith(expect.objectContaining({ method: 'get', url: '/tasks/backups/', signal }))
  await backupsApi.restore('20261016-010203', 'preflight', 'fixture-password', signal)
  expect(transport.request).toHaveBeenLastCalledWith(expect.objectContaining({ method: 'post', url: '/tasks/backups/20261016-010203/restore/', signal,
    data: { preflight_id: 'preflight', confirmation: '恢复备份', current_password: 'fixture-password' } }))
})

it('路径编码、查询和幂等请求头交给既有 Axios 链路', async () => {
  await sdk('users_retrieve', { path: { id: '中文 ?#' }, headers: { 'Idempotency-Key': 'fixture' } })
  const config = transport.request.mock.calls[0]![0]
  expect(config.url).toBe('/users/%E4%B8%AD%E6%96%87%20%3F%23/')
  expect(config.headers['Idempotency-Key']).toBe('fixture')
  expect(axios.getUri({ ...config, params: { selected: ['one', 'two'] } })).toContain('selected=one&selected=two')
})

it('multipart 上传保留文件内容并自动生成 boundary', async () => {
  const file = new File(['fixture'], 'fixture.txt', { type: 'text/plain' })
  await sdk('files_create', { contentType: 'multipart/form-data', body: { file, description: 'fixture' },
    headers: { 'content-TYPE': 'multipart/form-data; boundary=incorrect' } })
  const config = transport.request.mock.calls[0]![0]
  expect(config.data).toBeInstanceOf(FormData)
  expect(config.data.get('file')).toBe(file)
  expect(config.data.get('description')).toBe('fixture')
  expect(config.headers['Content-Type']).toBeUndefined()
  expect(Object.keys(config.headers).some(key => key.toLowerCase() === 'content-type')).toBe(false)
})

it('二进制下载返回 Blob；失败和取消不自动重放', async () => {
  const blob = new Blob(['fixture'])
  transport.request.mockResolvedValueOnce({ data: blob })
  expect(await sdk('files_download_retrieve', { path: { id: 'fixture' }, responseType: 'blob' })).toBe(blob)
  const failure = Object.assign(new Error('cancelled'), { __CANCEL__: true })
  transport.request.mockRejectedValueOnce(failure)
  await expect(backupsApi.status()).rejects.toBe(failure)
  expect(transport.request).toHaveBeenCalledTimes(2)
})

it('204 无响应体规范化为 undefined，与生成类型一致', async () => {
  transport.request.mockResolvedValueOnce({ status: 204, data: '' })
  expect(await sdk('auth_sessions_destroy', { path: { id: 'fixture' } })).toBeUndefined()
})

const unsafe = sdk as unknown as (operation: string, options?: unknown) => Promise<unknown>
it.each(['https://example.test/api/v1/users/', '//example.test/api/v1/users/', '/api/v1/users/?token=x', '/api/v1/users/#x', '/api/v1/users/\\x'])('拒绝越出固定 API 入口：%s', async path => {
  await expect(unsafe(path)).rejects.toThrow('Unknown SDK operation')
  expect(transport.request).not.toHaveBeenCalled()
})
it.each(['..', '.', 'x/y', 'x\\y', '\u0000', ''])('拒绝路径参数穿越：%s', async id => {
  await expect(unsafe('users_retrieve', { path: { id } })).rejects.toThrow('Invalid SDK path parameter')
  expect(transport.request).not.toHaveBeenCalled()
})
it('拒绝缺失和多余路径参数', async () => {
  await expect(unsafe('users_retrieve')).rejects.toThrow('Invalid SDK path parameter')
  await expect(unsafe('users_retrieve', { path: { id: 'fixture', extra: 'unexpected' } })).rejects.toThrow('Unexpected SDK path parameter')
  expect(transport.request).not.toHaveBeenCalled()
})
