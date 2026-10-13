import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('../src/api/request', () => ({ default: { post: vi.fn().mockResolvedValue({ data: {} }) } }))
import request from '../src/api/request'
import { approvalsApi, notificationsApi } from '../src/api'

describe('写请求幂等键', () => {
  beforeEach(() => vi.mocked(request.post).mockClear())

  it('审批创建支持调用方保留同一键用于失败重试', async () => {
    const payload = { title: '申请', request_type: 'other', content: '内容', assignee_username: 'admin' }
    await approvalsApi.create(payload, 'same-operation')
    await approvalsApi.create(payload, 'same-operation')
    expect(vi.mocked(request.post).mock.calls.map(call => call[2]?.headers?.['Idempotency-Key'])).toEqual(['same-operation', 'same-operation'])
  })

  it('独立发送通知生成不同操作键，决策接口也附带键', async () => {
    await notificationsApi.send({ recipient_ids: ['user'], title: '公告' })
    await notificationsApi.send({ recipient_ids: ['user'], title: '公告' })
    await approvalsApi.approve('id', '通过')
    await approvalsApi.reject('id', '驳回')
    const keys = vi.mocked(request.post).mock.calls.map(call => String(call[2]?.headers?.['Idempotency-Key']))
    expect(new Set(keys).size).toBe(4)
    expect(keys.every(key => /^[\x21-\x7e]{1,128}$/.test(key))).toBe(true)
  })
})
