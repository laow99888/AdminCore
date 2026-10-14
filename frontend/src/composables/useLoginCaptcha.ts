import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { loginCaptchaApi, type LoginCaptchaChallenge, type LoginCaptchaProof } from '@/api/loginCaptcha'

export function useLoginCaptcha(username: () => string) {
  const required = ref(false), challenge = ref<Extract<LoginCaptchaChallenge, { required: true }>>(), code = ref('')
  const loading = ref(false), error = ref<'load' | 'expired' | 'image' | ''>(''), expiresAt = ref(0), now = ref(Date.now())
  const seconds = computed(() => Math.max(0, Math.ceil((expiresAt.value - now.value) / 1000)))
  const ready = computed(() => !!challenge.value && !loading.value && seconds.value > 0)
  let generation = 0, alive = true, controller: AbortController | undefined
  function clear(resetRequired = true) {
    generation++; controller?.abort(); controller = undefined
    challenge.value = undefined; code.value = ''; expiresAt.value = 0; loading.value = false; error.value = ''
    if (resetRequired) required.value = false
  }
  function consume() { clear(false) }
  function imageFailed() { clear(false); error.value = 'image' }
  async function refresh() {
    clear(false); required.value = true
    const owner = username(), attempt = generation, active = new AbortController()
    controller = active; loading.value = true
    try {
      const value = await loginCaptchaApi.challenge(owner, active.signal)
      if (!alive || active.signal.aborted || attempt !== generation || owner !== username()) return
      required.value = value.required
      if (value.required) { challenge.value = value; now.value = Date.now(); expiresAt.value = now.value + value.expires_in * 1000 }
    } catch { if (alive && !active.signal.aborted && attempt === generation && owner === username()) error.value = 'load' }
    finally { if (alive && !active.signal.aborted && attempt === generation) loading.value = false }
  }
  function proof(): LoginCaptchaProof | undefined {
    if (challenge.value && expiresAt.value <= Date.now()) { clear(false); error.value = 'expired' }
    if (!ready.value || !code.value.trim()) return undefined
    return { captcha_id: challenge.value!.challenge_id, captcha_code: code.value.trim().toUpperCase() }
  }
  const stop = watch(username, () => clear(), { flush: 'sync' })
  const timer = window.setInterval(() => { now.value = Date.now(); if (challenge.value && seconds.value <= 0) { clear(false); error.value = 'expired' } }, 1000)
  onBeforeUnmount(() => { alive = false; clear(); stop(); window.clearInterval(timer) })
  return { required, challenge, code, loading, error, seconds, ready, clear, consume, imageFailed, refresh, proof }
}
