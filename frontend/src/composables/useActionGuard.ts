import { onActivated, onDeactivated, onScopeDispose } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { sessionIdentity } from '@/auth/sessionIdentity'
import { getTenantId } from '@/auth/tenantContext'

/** 确认框等 await 前捕获操作归属，恢复执行时复核会话、租户与页面生命周期。 */
export function useActionGuard() {
  const auth = useAuthStore()
  let active = true
  let generation = 0
  const retire = () => { active = false; generation++ }
  onScopeDispose(retire)
  onDeactivated(retire)
  onActivated(() => { active = true })
  const identity = () => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), getTenantId(), auth.user?.permissions])
  return () => {
    const owner = identity()
    const version = generation
    return () => active && version === generation && owner === identity()
  }
}
