<template>
  <section v-if="allowed" class="capacity-panel" :aria-label="uiText('我的文件容量')" :aria-busy="loading">
    <div class="capacity-summary"><strong>{{ uiText('我的文件容量') }}</strong>
      <span v-if="loading" role="status">{{ uiText('正在读取容量…') }}</span>
      <span v-else-if="failed" role="alert">{{ uiText('容量读取失败，请重试') }}</span>
      <template v-else-if="capacity"><span>{{ uiText('已使用 {p0}', { p0: fileBytes(capacity.used_bytes) }) }}</span>
        <span>{{ capacity.limit_bytes ? uiText('上限 {p0}', { p0: fileBytes(capacity.limit_bytes) }) : uiText('不限容量') }}</span></template>
      <el-button :disabled="loading" @click="loadOwn">{{ uiText('刷新') }}</el-button>
      <el-button v-if="admin" @click="openManager">{{ uiText('容量管理') }}</el-button>
    </div>
    <p class="capacity-note">{{ uiText('持久附件按上传者计入当前租户，历史版本和回收站继续占用。分片暂存及预览派生不在此统计内。') }}</p>
    <el-dialog :model-value="managing && admin" :title="uiText('容量管理')" width="min(520px, 94vw)" append-to-body :close-on-click-modal="false" :before-close="closeManager">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item :label="uiText('容量所属用户')">
          <el-select v-if="canSearch" v-model="target" filterable remote :remote-method="searchUsers" :loading="searching" :disabled="busy" :aria-label="uiText('容量所属用户')" :placeholder="uiText('搜索用户名')" @change="loadTarget">
            <el-option :value="auth.user!.id" :label="auth.user!.username" />
            <el-option v-for="user in users" :key="user.id" :value="user.id" :label="user.username" />
          </el-select><span v-else>{{ auth.user?.username }}</span>
        </el-form-item>
        <p v-if="searchFailed" role="alert">{{ uiText('用户搜索失败，请重试') }}</p>
        <p v-if="targetLoading" role="status">{{ uiText('正在读取容量…') }}</p>
        <div v-else-if="targetFailed" role="alert"><p>{{ uiText('容量读取失败，请重试') }}</p><el-button @click="loadTarget">{{ uiText('重试') }}</el-button></div>
        <template v-else-if="targetCapacity"><p>{{ uiText('已使用 {p0}', { p0: fileBytes(targetCapacity.used_bytes) }) }}</p>
          <el-form-item :label="uiText('容量上限（MiB，0表示不限）')"><el-input-number v-model="draft" :min="0" :max="Number.MAX_SAFE_INTEGER / 1048576" :disabled="busy" :aria-label="uiText('容量上限（MiB，0表示不限）')" controls-position="right" /></el-form-item>
          <p class="capacity-note">{{ uiText('降低上限不会删除文件，超过上限时暂停新增上传。') }}</p></template>
        <p v-if="saveError" role="alert">{{ saveError }}</p>
        <el-button native-type="submit" type="primary" :loading="busy" :disabled="targetLoading || targetFailed || !targetCapacity || !validLimit || draftBytes === targetCapacity.limit_bytes">{{ uiText('保存容量上限') }}</el-button>
        <el-button :disabled="busy" @click="closeManager">{{ uiText('关闭') }}</el-button>
      </el-form>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './documentMessages'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { uiText } from '@/i18n/uiText'
import { usersApi, type UserRow } from '@/api'
import { responseStatus } from '@/api/request'
import { fileBytes, fileDocumentsApi, type FileCapacity } from '@/api/fileDocuments'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
const props = defineProps<{ refreshKey: number }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const allowed = computed(() => auth.can('file:read') && !auth.user?.must_change_password && modules.enabled('files'))
const admin = computed(() => allowed.value && auth.can('file:upload') && Boolean(auth.user?.is_staff || auth.user?.is_superuser))
const canSearch = computed(() => admin.value && auth.can('user:read') && modules.pathEnabled('/users'))
const identity = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, auth.user?.must_change_password, tenants.currentId, allowed.value, canSearch.value]))
const capacity = ref<FileCapacity | null>(null), loading = ref(false), failed = ref(false), managing = ref(false)
const target = ref(''), targetCapacity = ref<FileCapacity | null>(null), targetLoading = ref(false), targetFailed = ref(false)
const draft = ref<number | undefined>(0), busy = ref(false), saveError = ref(''), users = ref<UserRow[]>([]), searching = ref(false), searchFailed = ref(false)
const draftBytes = computed(() => (draft.value ?? NaN) * 1048576)
const validLimit = computed(() => Number.isSafeInteger(draftBytes.value) && draftBytes.value >= 0)
let ownGeneration = 0, targetGeneration = 0, searchGeneration = 0, mutationGeneration = 0
let ownController: AbortController | null = null, targetController: AbortController | null = null
async function loadOwn() {
  const tick = ++ownGeneration, owner = identity.value
  ownController?.abort(); capacity.value = null; loading.value = false; failed.value = false
  if (!allowed.value) return
  ownController = new AbortController(); loading.value = true
  const valid = () => tick === ownGeneration && owner === identity.value
  try { const result = await fileDocumentsApi.capacity(undefined, ownController.signal); if (valid()) capacity.value = result }
  catch { if (valid()) failed.value = true }
  finally { if (valid()) loading.value = false }
}
function openManager() { if (!admin.value) return; managing.value = true; target.value = auth.user!.id; users.value = []; saveError.value = ''; void loadTarget() }
function closeManager() {
  if (busy.value) return
  managing.value = false; mutationGeneration++; targetGeneration++; searchGeneration++; targetController?.abort()
  targetCapacity.value = null; users.value = []; saveError.value = ''; searching.value = false; searchFailed.value = false
}
async function loadTarget() {
  const tick = ++targetGeneration, owner = identity.value, id = target.value
  targetController?.abort(); targetCapacity.value = null; targetLoading.value = false; targetFailed.value = false; saveError.value = ''
  if (!id || !managing.value || !admin.value) return
  targetController = new AbortController(); targetLoading.value = true
  const valid = () => tick === targetGeneration && owner === identity.value && id === target.value && managing.value
  try { const result = await fileDocumentsApi.capacity(id, targetController.signal); if (valid()) { targetCapacity.value = result; draft.value = result.limit_bytes / 1048576 } }
  catch { if (valid()) targetFailed.value = true }
  finally { if (valid()) targetLoading.value = false }
}
async function searchUsers(search: string) {
  const tick = ++searchGeneration, owner = identity.value
  users.value = []; searchFailed.value = false; searching.value = false
  if (!canSearch.value || !managing.value || !search.trim()) return
  searching.value = true
  const valid = () => tick === searchGeneration && owner === identity.value && managing.value
  try { const result = await usersApi.list({ search: search.trim(), is_active: true, page: 1, page_size: 20 }); if (valid()) users.value = result.items.filter(user => user.id !== auth.user?.id) }
  catch { if (valid()) searchFailed.value = true }
  finally { if (valid()) searching.value = false }
}
async function save() {
  if (!admin.value || !managing.value || busy.value || targetLoading.value || targetFailed.value || !targetCapacity.value) return
  if (!validLimit.value) { saveError.value = uiText('请输入有效容量，最多精确到一个字节'); return }
  const tick = ++mutationGeneration, owner = identity.value, id = target.value, version = targetCapacity.value.version
  const valid = () => tick === mutationGeneration && owner === identity.value && id === target.value && managing.value
  busy.value = true; saveError.value = ''
  try {
    const result = await fileDocumentsApi.saveCapacity(id, draftBytes.value, version)
    if (!valid()) return
    targetCapacity.value = result; draft.value = result.limit_bytes / 1048576
    if (id === auth.user?.id) capacity.value = result
    ElMessage.success(uiText('容量上限已保存'))
  } catch (error) {
    if (!valid()) return
    saveError.value = uiText(responseStatus(error) === 409 ? '容量配置已变更，请重新读取后再编辑。' : '容量保存失败，输入已保留')
    if (responseStatus(error) === 409) { targetFailed.value = true; targetCapacity.value = null }
  } finally { if (valid()) busy.value = false }
}
function cancel() {
  ownGeneration++; targetGeneration++; searchGeneration++; mutationGeneration++; ownController?.abort(); targetController?.abort()
  capacity.value = null; targetCapacity.value = null; loading.value = false; failed.value = false; busy.value = false
  managing.value = false; users.value = []; searching.value = false; searchFailed.value = false
}
watch(identity, () => { cancel(); void loadOwn() }, { immediate: true })
watch(() => props.refreshKey, () => { void loadOwn() })
onBeforeUnmount(cancel)
</script>
<style scoped>
.capacity-panel { border: 1px solid var(--el-border-color-lighter); border-radius: var(--el-border-radius-base); padding: 12px; margin-bottom: 16px; }
.capacity-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.capacity-summary .el-button { margin-left: 0; }
.capacity-note { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; margin: 8px 0 0; }
.el-select { width: 100%; }
.el-input-number { max-width: 100%; }
@media (max-width: 640px) { .capacity-summary .el-button { min-height: 44px; } }
</style>
