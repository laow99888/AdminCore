import { computed, onActivated, onDeactivated, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter, type Router } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'

interface Draft {
  dirty: () => boolean
  busy: () => boolean
  active: () => boolean
  discard: () => void
  message?: () => string
}

const drafts = new Set<Draft>()
const routers = new Map<Router, { owners: number; dispose: () => void }>()
let confirmation: Promise<boolean> | undefined
const securityPaths = new Set(['/login', '/change-password', '/403', '/unavailable', '/500'])

async function confirmDrafts(values: Draft[]) {
  if (values.some(value => value.active() && value.busy())) return false
  if (!values.some(value => value.active() && value.dirty())) return true
  // A settings page can contain several drafts; one action asks once.
  if (!confirmation) {
    const changed = values.filter(value => value.active() && value.dirty())
    const message = changed.length === 1 ? changed[0]?.message?.() : undefined
    confirmation = ElMessageBox.confirm(message || uiText('尚有未保存的修改，确定放弃吗？'), uiText('提示'), {
      confirmButtonText: uiText('确定'), cancelButtonText: uiText('取消'), type: 'warning',
      closeOnClickModal: false,
    }).then(() => true, () => false).finally(() => { confirmation = undefined })
  }
  const accepted = await confirmation
  return accepted && !values.some(value => value.active() && value.busy())
}

/** Call before an action which remounts the current page, such as changing its language. */
export async function confirmPendingForms() { return confirmDrafts([...drafts]) }

function beforeUnload(event: BeforeUnloadEvent) {
  if ([...drafts].some(value => value.active() && (value.dirty() || value.busy()))) {
    event.preventDefault(); event.returnValue = ''
  }
}

/** In-memory baseline only. The owner clears fields when a draft is closed or access is revoked. */
export function useUnsavedChanges(options: {
  source: () => unknown
  active?: () => boolean
  busy: () => boolean
  canEdit?: () => boolean
  allowForcedPassword?: boolean
  message?: () => string
  clear: () => void
}) {
  const router = useRouter(), route = useRoute(), auth = useAuthStore()
  const path = route.path
  const owner = auth.user?.id
  const mounted = ref(true)
  const allowed = computed(() => auth.isAuthenticated && !!auth.user && auth.user.id === owner && (!auth.user.must_change_password || options.allowForcedPassword === true) && (options.canEdit?.() ?? true))
  const enabled = computed(() => mounted.value && allowed.value && (options.active?.() ?? true))
  const baseline = ref(JSON.stringify(options.source()))
  const dirty = computed(() => enabled.value && JSON.stringify(options.source()) !== baseline.value)
  function markClean() { baseline.value = JSON.stringify(options.source()) }
  function discard() { options.clear(); markClean() }
  function isSessionCurrent() { return mounted.value && auth.isAuthenticated && auth.user?.id === owner && (!auth.user?.must_change_password || options.allowForcedPassword === true) && router.currentRoute.value.path === path }
  const draft: Draft = {
    active: () => enabled.value && router.currentRoute.value.path === path,
    dirty: () => dirty.value, busy: options.busy, discard, message: options.message,
  }
  if (!drafts.size) window.addEventListener('beforeunload', beforeUnload)
  drafts.add(draft)
  let state = routers.get(router)
  if (!state) {
    state = { owners: 0, dispose: router.beforeEach(async to => {
      if (securityPaths.has(to.path)) {
        if (confirmation) ElMessageBox.close()
        for (const value of drafts) if (value.active()) value.discard()
        return true
      }
      if (to.path === router.currentRoute.value.path) return true
      return confirmPendingForms()
    }) }
    routers.set(router, state)
  }
  state.owners++
  watch(() => options.active?.() ?? true, active => { if (active) markClean(); else discard() }, { flush: 'sync' })
  watch(allowed, value => { if (!value) { if (confirmation) ElMessageBox.close(); discard() } }, { flush: 'sync' })
  onActivated(() => { mounted.value = true })
  onDeactivated(() => { mounted.value = false; discard() })
  onScopeDispose(() => {
    mounted.value = false
    discard()
    drafts.delete(draft)
    if (!drafts.size) window.removeEventListener('beforeunload', beforeUnload)
    const current = routers.get(router)!
    if (--current.owners === 0) { current.dispose(); routers.delete(router) }
  })
  return { dirty, markClean, confirmDiscard: () => confirmDrafts([draft]), discard,
    isSessionCurrent, isCurrent: () => isSessionCurrent() && allowed.value }
}
