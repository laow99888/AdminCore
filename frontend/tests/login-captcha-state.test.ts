import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
vi.mock('../src/api/loginCaptcha', () => ({ loginCaptchaApi: { challenge: vi.fn() } }))
import { loginCaptchaApi, type LoginCaptchaChallenge } from '../src/api/loginCaptcha'
import { useLoginCaptcha } from '../src/composables/useLoginCaptcha'
const value: LoginCaptchaChallenge = { required: true, challenge_id: '00000000-0000-4000-8000-000000000001', image: 'fixture-png', expires_in: 120 }
function harness() {
  const username = ref('old'); let state!: ReturnType<typeof useLoginCaptcha>
  const wrapper = mount(defineComponent({ setup() { state = useLoginCaptcha(() => username.value); return () => h('div') } }))
  return { username, state, wrapper }
}
describe('登录挑战归属、过期与单次消费', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(loginCaptchaApi.challenge).mockResolvedValue(value) })
  afterEach(() => vi.useRealTimers())
  it('用户名变更abort旧请求，迟到成功不恢复旧挑战', async () => {
    let complete!: (data: LoginCaptchaChallenge) => void
    vi.mocked(loginCaptchaApi.challenge).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const { state, username } = harness(); const pending = state.refresh()
    const signal = vi.mocked(loginCaptchaApi.challenge).mock.calls[0]![1]!
    username.value = 'new'; expect(signal.aborted).toBe(true)
    complete(value); await pending
    expect(state.required.value).toBe(false); expect(state.challenge.value).toBeUndefined()
  })
  it('新refresh赢过旧失败，卸载abort并拒绝迟到数据', async () => {
    let reject!: (reason: Error) => void
    vi.mocked(loginCaptchaApi.challenge).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    const { state, wrapper } = harness(); const pending = state.refresh(); await state.refresh()
    reject(new Error('stale')); await pending
    expect(state.challenge.value).toEqual(value); expect(state.error.value).toBe('')
    let complete!: (data: LoginCaptchaChallenge) => void
    vi.mocked(loginCaptchaApi.challenge).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    const leaving = state.refresh(); const signal = vi.mocked(loginCaptchaApi.challenge).mock.calls.at(-1)![1]!
    wrapper.unmount(); expect(signal.aborted).toBe(true); complete(value); await leaving
    expect(state.challenge.value).toBeUndefined(); expect(state.code.value).toBe('')
  })
  it('倒计时与提交瞬间过期均不能复用；trim upper保留内部字符', async () => {
    vi.useFakeTimers(); const { state } = harness(); await state.refresh()
    state.code.value = ' ab cd '; expect(state.proof()?.captcha_code).toBe('AB CD')
    vi.advanceTimersByTime(120001); await flushPromises()
    expect(state.proof()).toBeUndefined(); expect(state.challenge.value).toBeUndefined(); expect(state.error.value).toBe('expired')
    await state.refresh(); state.code.value = 'ABCDE'; state.consume()
    expect(state.required.value).toBe(true); expect(state.proof()).toBeUndefined(); expect(state.code.value).toBe('')
  })
  it('请求失败保留required可重试，服务端取消gate清除敏感数据', async () => {
    const { state } = harness(); vi.mocked(loginCaptchaApi.challenge).mockRejectedValueOnce(new Error('failed'))
    await state.refresh(); expect(state.error.value).toBe('load'); expect(state.required.value).toBe(true)
    vi.mocked(loginCaptchaApi.challenge).mockResolvedValueOnce({ required: false }); await state.refresh()
    expect(state.required.value).toBe(false); expect(state.challenge.value).toBeUndefined()
  })
})
