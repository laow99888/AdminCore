<template>
  <el-card v-if="canManage" shadow="never" class="service-identities">
    <template #header><div class="heading"><div><h2>{{ uiText('机器集成身份') }}</h2><p>{{ uiText('机器使用独立身份与专用只读角色，不受创建人改密或离职影响；身份固定归属当前租户。') }}</p></div><BaseButton :disabled="busy || loading" @click="newIdentity">{{ uiText('创建机器身份') }}</BaseButton><BaseButton variant="ghost" :disabled="busy || loading" @click="load">{{ uiText('刷新机器身份') }}</BaseButton></div></template>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <p v-if="loading" role="status">{{ uiText('正在加载机器身份') }}</p>
    <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-index="false" :show-actions="true" :action-width="280"  @update:current-page="changePage" @update:page-size="changeSize">
      <template #actions="{ row }"><BaseButton variant="ghost" :disabled="busy || loading" @click="editIdentity(row)">{{ uiText('编辑身份') }}</BaseButton><BaseButton variant="ghost" :disabled="busy || loading" @click="toggleIdentity(row)">{{ uiText(row.is_active ? '停用身份' : '启用身份') }}</BaseButton><BaseButton variant="ghost" :disabled="busy || loading" @click="selectIdentity(row)">{{ uiText('管理机器凭证') }}</BaseButton></template>
    </BaseTable>
    <el-alert v-if="!loading && !roles.length" :title="uiText('没有可授予的专用只读角色。请先在角色管理创建只含开放只读能力的角色，并配置其数据范围与字段权限。')" type="info" :closable="false" />
    <el-dialog v-model="identityOpen" :title="uiText(editing ? '编辑机器身份' : '创建机器身份')" width="min(600px, 94vw)" :close-on-click-modal="false" destroy-on-close>
      <el-form label-position="top" @submit.prevent="confirmIdentity">
        <el-form-item :label="uiText('身份名称')"><el-input v-model.trim="draft.name" maxlength="80" :disabled="busy" :aria-label="uiText('身份名称')" /></el-form-item>
        <el-form-item :label="uiText('用途说明')"><el-input v-model.trim="draft.description" maxlength="300" :disabled="busy" :aria-label="uiText('用途说明')" /></el-form-item>
        <el-form-item :label="uiText('专用只读角色')"><el-checkbox-group v-model="draft.role_ids" :disabled="busy"><el-checkbox v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</el-checkbox></el-checkbox-group></el-form-item>
        <p>{{ uiText('角色必须仅包含当前启用的开放只读能力；不能授予交互登录或管理权限。') }}</p>
        <BaseButton native-type="submit" :disabled="busy || !validIdentity">{{ uiText('确认保存身份') }}</BaseButton>
      </el-form>
    </el-dialog>
    <section v-if="selected" class="credentials" :aria-label="uiText('机器凭证')">
      <h3>{{ uiText('机器凭证') }} · {{ selected.name }}</h3>
      <el-alert :title="uiText('停用永久撤销现有密钥；重新启用后须重新签发。角色、字段、数据范围及租户状态在每次请求时复核。只展示最近100条凭证。')" type="info" :closable="false" />
      <el-form label-position="top" @submit.prevent="prepareIssue">
        <el-form-item :label="uiText('凭证名称')"><el-input v-model.trim="credentialDraft.name" maxlength="80" :disabled="busy || credentialLoading || !selected.is_active" :aria-label="uiText('凭证名称')" /></el-form-item>
        <el-form-item :label="uiText('只读能力')"><el-checkbox-group v-model="credentialDraft.scopes" :disabled="busy || !selected.is_active"><el-checkbox v-for="scope in scopes" :key="scope.code" :value="scope.code">{{ uiText(scope.label) }}</el-checkbox></el-checkbox-group></el-form-item>
        <el-form-item :label="uiText('有效天数')"><el-input-number v-model="days" :min="1" :max="90" :disabled="busy || !selected.is_active" :aria-label="uiText('有效天数')" /></el-form-item>
        <BaseButton native-type="submit" :disabled="busy || credentialLoading || !validCredential || !selected.is_active">{{ uiText('签发机器凭证') }}</BaseButton>
      </el-form>
      <BaseTable :data="credentials" :columns="credentialColumns" :loading="credentialLoading" :show-pagination="false" :show-index="false" :show-actions="true" :action-width="200"><template #actions="{ row }"><BaseButton variant="ghost" :disabled="busy || credentialLoading || !selected.is_active || invalid(row)" @click="prepareCredential('rotate', row)">{{ uiText('轮换密钥') }}</BaseButton><BaseButton variant="ghost" :disabled="busy || credentialLoading || !!row.revoked_at" @click="prepareCredential('revoke', row)">{{ uiText('撤销凭证') }}</BaseButton></template></BaseTable>
    </section>
    <PasswordConfirmationDialog v-model="confirmationOpen" :description="confirmationDescription" :execute="execute" :disabled="!canManage" :confirm-text="uiText('确认')" :error-text="uiText('操作未确认，请检查密码、当前角色与权限。版本冲突请关闭后刷新重试。')" @busy="busy = $event" />
    <el-dialog v-model="secretOpen" :title="uiText('机器密钥仅展示一次')" width="min(600px, 94vw)" :close-on-click-modal="false" destroy-on-close @closed="clearSecret"><p>{{ uiText('请立即保存到密钥管理工具。不要把密钥写入网址、日志或代码。') }}</p><label for="service-identity-secret">{{ uiText('机器 API 密钥') }}</label><textarea id="service-identity-secret" :value="secret" readonly autocomplete="off" spellcheck="false" rows="3" /><p>{{ uiText('请求头：Authorization: ApiToken 加上密钥。仅支持独立开放 API 地址。') }}</p><template #footer><BaseButton @click="clearSecret">{{ uiText('已保存，关闭') }}</BaseButton></template></el-dialog>
  </el-card>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { BaseButton, BaseTable } from '@/components'
import PasswordConfirmationDialog from '@/components/auth/PasswordConfirmationDialog.vue'
import { serviceIdentitiesApi as api, type ServiceIdentity } from '@/api/serviceIdentities'
import { apiCredentialsApi, type APICredential } from '@/api/apiCredentials'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { getAccessToken } from '@/auth/tokenStorage'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { uiText } from '@/i18n/uiText'
const auth = useAuthStore(), tenants = useTenantStore()
const canManage = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser) && auth.can('api_credential:manage'))
const rows = ref<ServiceIdentity[]>([]), roles = ref<{ id: string; name: string }[]>([]), scopes = ref<{ code: string; label: string }[]>([])
const loading = ref(false), credentialLoading = ref(false), busy = ref(false), error = ref(''), page = ref(1), pageSize = ref(10), total = ref(0)
const selected = ref<ServiceIdentity | null>(null), editing = ref<ServiceIdentity | null>(null), target = ref<ServiceIdentity | null>(null)
const credentials = ref<APICredential[]>([]), credentialTarget = ref<APICredential | null>(null)
const identityOpen = ref(false), confirmationOpen = ref(false), secretOpen = ref(false), secret = ref(''), days = ref(30)
const draft = ref({ name: '', description: '', role_ids: [] as string[] }), credentialDraft = ref({ name: '', scopes: [] as string[] })
const operation = ref<'create' | 'edit' | 'toggle' | 'issue' | 'rotate' | 'revoke'>('create')
const validIdentity = computed(() => !!draft.value.name.trim() && draft.value.role_ids.length > 0 && draft.value.role_ids.length <= 16)
const validCredential = computed(() => !!credentialDraft.value.name.trim() && credentialDraft.value.scopes.length > 0 && days.value >= 1 && days.value <= 90)
const confirmationDescription = computed(() => uiText(operation.value === 'toggle' ? '确认变更身份状态？停用后已有密钥永久失效。' : operation.value === 'rotate' ? '确认轮换机器密钥？旧密钥立即失效，新密钥仅展示一次。' : operation.value === 'revoke' ? '确认撤销机器凭证？撤销后不能恢复。' : '确认保存机器身份或签发只读凭证？授权仍受当前角色、数据范围和字段权限约束。'))
const time = (value: string | null) => value ? new Date(value).toLocaleString() : '—'
const columns = computed(() => [{ prop: 'name', label: uiText('身份名称'), width: 180 }, { prop: 'description', label: uiText('用途说明'), width: 260 }, { prop: 'is_active', label: uiText('状态'), width: 100, render: (value: boolean) => uiText(value ? '已启用' : '已停用') }, { prop: 'version', label: uiText('版本'), width: 90 }])
const credentialColumns = computed(() => [{ prop: 'name', label: uiText('凭证名称'), width: 180 }, { prop: 'scopes', label: uiText('只读能力'), width: 200, render: (value: string[]) => value.join(', ') }, { prop: 'expires_at', label: uiText('过期时间'), width: 200, render: time }, { prop: 'revoked_at', label: uiText('撤销时间'), width: 200, render: time }, { prop: 'version', label: uiText('版本'), width: 90 }])
let alive = true, generation = 0, controller: AbortController | undefined, detailController: AbortController | undefined
function clearSecret() { secret.value = ''; secretOpen.value = false }
function invalid(row: APICredential) { return !!row.revoked_at || new Date(row.expires_at).getTime() <= Date.now() }
async function load() {
  if (!canManage.value || busy.value) return
  controller?.abort(); const active = controller = new AbortController(), owner = generation, token = getAccessToken()
  loading.value = true; error.value = ''
  try {
    const [result, choices, capabilities] = await Promise.all([api.list(page.value, pageSize.value, active.signal), api.roles(active.signal), apiCredentialsApi.scopes(active.signal)])
    if (!alive || owner !== generation || controller !== active || !tokensBelongToSameSession(token, getAccessToken())) return
    rows.value = result.items; total.value = result.pagination.total; roles.value = choices; scopes.value = capabilities
    if (selected.value) { selected.value = rows.value.find(row => row.id === selected.value?.id) || null; if (selected.value) await loadCredentials(selected.value); else credentials.value = [] }
  } catch { if (alive && owner === generation && !active.signal.aborted) error.value = uiText('机器身份加载失败，请刷新重试。') }
  finally { if (alive && controller === active) loading.value = false }
}
async function loadCredentials(row: ServiceIdentity) {
  detailController?.abort(); const active = detailController = new AbortController(), owner = generation, token = getAccessToken()
  credentialLoading.value = true; credentials.value = []
  try { const result = await api.credentials(row.id, active.signal); if (alive && owner === generation && selected.value?.id === row.id && detailController === active && tokensBelongToSameSession(token, getAccessToken())) credentials.value = result }
  catch { if (alive && owner === generation && !active.signal.aborted) error.value = uiText('机器凭证加载失败，请刷新重试。') }
  finally { if (alive && detailController === active) credentialLoading.value = false }
}
function changePage(value: number) { if (!busy.value) { page.value = value; selected.value = null; credentials.value = []; void load() } }
function changeSize(value: number) { if (!busy.value) { pageSize.value = value; page.value = 1; selected.value = null; credentials.value = []; void load() } }
function newIdentity() { if (busy.value) return; editing.value = null; draft.value = { name: '', description: '', role_ids: [] }; identityOpen.value = true }
function editIdentity(row: ServiceIdentity) { if (busy.value) return; editing.value = row; draft.value = { name: row.name, description: row.description, role_ids: [...row.role_ids] }; identityOpen.value = true }
function confirmIdentity() { if (!validIdentity.value || busy.value) return; target.value = editing.value; operation.value = editing.value ? 'edit' : 'create'; confirmationOpen.value = true }
function toggleIdentity(row: ServiceIdentity) { target.value = row; operation.value = 'toggle'; confirmationOpen.value = true }
function selectIdentity(row: ServiceIdentity) { selected.value = row; credentialDraft.value = { name: '', scopes: [] }; clearSecret(); void loadCredentials(row) }
function prepareIssue() { if (!selected.value?.is_active || !validCredential.value || busy.value) return; target.value = selected.value; operation.value = 'issue'; clearSecret(); confirmationOpen.value = true }
function prepareCredential(action: 'rotate' | 'revoke', row: APICredential) { if (!selected.value || busy.value || row.revoked_at || (action === 'rotate' && (!selected.value.is_active || invalid(row)))) return; target.value = selected.value; credentialTarget.value = row; operation.value = action; clearSecret(); confirmationOpen.value = true }
async function execute(password: string) {
  if (!canManage.value) throw new Error('permission changed')
  const owner = generation, token = getAccessToken(), identity = target.value, action = operation.value
  let issued = ''
  if (action === 'create' || action === 'edit') {
    if (!validIdentity.value) throw new Error('invalid identity')
    const body = { ...draft.value, role_ids: [...draft.value.role_ids] }
    if (action === 'create') await api.create(body, password)
    else { if (!identity) throw new Error('missing identity'); await api.update(identity, body, password) }
  } else {
    if (!identity) throw new Error('missing identity')
    if (action === 'toggle') await api.update(identity, { is_active: !identity.is_active }, password)
    else if (action === 'issue') { if (!validCredential.value) throw new Error('invalid credential'); issued = (await api.issue(identity.id, { ...credentialDraft.value, scopes: [...credentialDraft.value.scopes], expires_at: new Date(Date.now() + days.value * 86400000).toISOString() }, password)).token }
    else { if (!credentialTarget.value) throw new Error('missing credential'); if (action === 'rotate') issued = (await api.rotate(identity.id, credentialTarget.value, password)).token; else await api.revoke(identity.id, credentialTarget.value, password) }
  }
  if (!alive || owner !== generation || !canManage.value || !tokensBelongToSameSession(token, getAccessToken())) return
  identityOpen.value = false; draft.value = { name: '', description: '', role_ids: [] }; credentialDraft.value = { name: '', scopes: [] }
  if (issued) { secret.value = issued; secretOpen.value = true }
}
watch(confirmationOpen, value => { if (!value) { target.value = null; credentialTarget.value = null; if (alive) void load() } })
watch(busy, value => { if (!value && !confirmationOpen.value && alive) void load() })
watch(secretOpen, value => { if (!value) secret.value = '' })
function reset() { generation++; controller?.abort(); detailController?.abort(); rows.value = []; roles.value = []; scopes.value = []; credentials.value = []; selected.value = null; editing.value = null; total.value = 0; page.value = 1; identityOpen.value = false; confirmationOpen.value = false; clearSecret(); draft.value = { name: '', description: '', role_ids: [] }; credentialDraft.value = { name: '', scopes: [] }; loading.value = false; credentialLoading.value = false }
watch([() => auth.user?.id, () => auth.user?.permissions?.join(','), () => tenants.currentId, canManage], () => { reset(); if (canManage.value) void load() })
onBeforeRouteLeave(() => { clearSecret(); identityOpen.value = false })
onBeforeUnmount(() => { alive = false; reset() })
void load()
</script>
<style scoped>
.service-identities { min-width: 0; }
.heading { display: flex; align-items: start; flex-wrap: wrap; gap: var(--spacing-md); }
.heading > div { flex: 1; min-width: min(100%, 260px); }
h2, h3 { margin-top: 0; }
p { line-height: 1.6; overflow-wrap: anywhere; }
.credentials { display: grid; gap: var(--spacing-md); margin-top: var(--spacing-lg); }
.el-form { max-width: 600px; }
textarea { box-sizing: border-box; width: 100%; display: block; padding: var(--spacing-sm); background: var(--color-bg-card); color: var(--color-text-primary); border: 1px solid var(--color-border); resize: vertical; }
</style>
