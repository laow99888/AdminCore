import { beforeEach, expect, it } from 'vitest'
import publicRequest from '../src/api/publicRequest'

beforeEach(() => localStorage.clear())

it.each([['en-US', 'en'], ['zh-CN', 'zh-Hans']])('公开传输发送当前语言且不携带JWT %s', async (language, expected) => {
  localStorage.setItem('language', language!)
  localStorage.setItem('token', 'must-not-be-sent')
  const result = await publicRequest.get('/isolated-language-check/', {
    adapter: async config => ({ status: 200, statusText: 'OK', headers: {}, config, data: {
      language: config.headers.get('Accept-Language'), authorization: config.headers.get('Authorization'),
    } }),
  })
  expect(result.data.language).toBe(expected)
  expect(result.data.authorization).toBeUndefined()
})
