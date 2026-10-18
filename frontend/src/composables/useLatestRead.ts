import { onScopeDispose, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { sessionIdentity } from '@/auth/sessionIdentity'

/** 查询及身份共用世代，旧响应不能覆盖分页或切换身份后的状态。 */
export function useLatestRead(clear: () => void) {
  const auth = useAuthStore()
  const identity = () => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password])
  let generation = 0, active = true
  watch(identity, () => { generation++; clear() }, { flush: 'sync' })
  onScopeDispose(() => { active = false; generation++; clear() })
  return () => {
    const current = ++generation, owner = identity()
    return () => active && current === generation && owner === identity()
  }
}
