import { expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { request: vi.fn() } }))
import request from '../src/api/request'
import { announcementsApi } from '../src/api/announcements'
it('公告保存同时携带content_format并保留原有幂等键与版本', async () => {
  vi.mocked(request.request).mockResolvedValue({ data: { data: {} } })
  const body = { title: 'title', content: '<p>body</p>', content_format: 'html' as const, version: 2 }
  await announcementsApi.save('a1', body, 'fixed-key')
  expect(request.request).toHaveBeenCalledWith({ url: '/notifications/announcements/manage/a1/', method: 'patch', data: body, headers: { 'Idempotency-Key': 'fixed-key' } })
})
