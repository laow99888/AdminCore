<template>
  <AppLayout>
    <section class="credentials-page">
      <div class="heading">
        <div><h1>{{ uiText('开放凭证') }}</h1><p>{{ uiText('只读开放 API 使用独立密钥；可读取已授权摘要和显式登记的业务资源，遵守当前字段与数据范围。') }}</p></div>
        <BaseButton variant="ghost" :loading="loading" :disabled="loading || busy" @click="load">{{ uiText('刷新') }}</BaseButton>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert :title="uiText('密钥不能登录、修改业务或管理账号。修改密码、全部设备下线、权限撤销及到期后会失效。')" type="info" :closable="false" show-icon />
      <el-card v-if="canCreate" shadow="never">
        <template #header>{{ uiText('创建本人开放凭证') }}</template>
        <el-form label-position="top" @submit.prevent="prepareCreate">
          <el-form-item :label="uiText('名称')"><el-input v-model.trim="draft.name" :aria-label="uiText('名称')" maxlength="80" :disabled="busy || loading" /></el-form-item>
          <el-form-item :label="uiText('只读能力')">
            <el-checkbox-group v-model="draft.scopes" :disabled="busy || loading"><el-checkbox v-for="scope in scopes" :key="scope.code" :value="scope.code">{{ uiText(scope.label) }}</el-checkbox></el-checkbox-group>
            <p v-if="!scopes.length">{{ uiText('当前没有可签发的只读能力，请检查模块和本人权限。') }}</p>
          </el-form-item>
          <el-form-item :label="uiText('有效天数')"><el-input-number v-model="days" :min="1" :max="90" :aria-label="uiText('有效天数')" :disabled="busy || loading" /></el-form-item>
          <BaseButton native-type="submit" :disabled="!validDraft || busy || loading">{{ uiText('确认创建') }}</BaseButton>
        </el-form>
      </el-card>
      <p v-if="loading" role="status">{{ uiText('正在加载开放凭证') }}</p>
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-index="false" :show-actions="true" :action-width="280" @update:current-page="changePage" @update:page-size="changeSize">
        <template #actions="{ row }">
          <BaseButton variant="ghost" :disabled="busy || loading" @click="statisticsTarget = row">{{ uiText('调用统计') }}</BaseButton>
          <BaseButton v-if="canCreate && canRevoke" variant="ghost" :disabled="busy || loading || !!row.revoked_at || new Date(row.expires_at).getTime() <= Date.now()" @click="prepareRotate(row)">{{ uiText('轮换密钥') }}</BaseButton>
          <BaseButton v-if="canRevoke" variant="ghost" :disabled="busy || loading || !!row.revoked_at" @click="prepareRevoke(row)">{{ uiText('撤销凭证') }}</BaseButton>
        </template>
      </BaseTable>
      <ServiceIdentityPanel />
      <PasswordConfirmationDialog v-model="confirmationOpen" :description="confirmationDescription" :execute="execute" :disabled="operation === 'create' ? !canCreate || !validDraft : !canRevoke || !target || (operation === 'rotate' && !canCreate)" :confirm-text="uiText('确认')" :error-text="uiText('操作未确认，请检查密码、权限、版本和有效期后重试；轮换冲突请关闭后刷新。')" @busy="busy = $event" />
      <CredentialStatisticsDialog :credential="statisticsTarget" @close="statisticsTarget = null" />
      <el-dialog v-model="secretOpen" :title="uiText('密钥仅展示一次')" width="min(600px, 94vw)" :close-on-click-modal="false" destroy-on-close @closed="clearSecret">
        <p>{{ uiText('请立即保存到你的密钥管理工具；关闭后无法再次查看。不要把密钥放入网址、日志或代码仓库。') }}</p>
        <label for="issued-api-secret">{{ uiText('开放 API 密钥') }}</label>
        <textarea id="issued-api-secret" :value="issuedSecret" readonly autocomplete="off" spellcheck="false" rows="3" />
        <p>{{ uiText('请求头格式：Authorization: ApiToken 加上密钥。仅支持独立开放 API 地址。') }}</p>
        <code>/api/v1/api-credentials/tasks/</code><br /><code>/api/v1/api-credentials/work-items/</code>
        <template #footer><BaseButton @click="secretOpen = false">{{ uiText('已保存，关闭') }}</BaseButton></template>
      </el-dialog>
    </section>
  </AppLayout>
</template>

<script setup lang="ts">
import { formatDateTime } from '@/utils/dateTime'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseTable } from '@/components'
import PasswordConfirmationDialog from '@/components/auth/PasswordConfirmationDialog.vue'
import { apiCredentialsApi, type APICredential } from '@/api/apiCredentials'
import { useAuthStore } from '@/stores/auth'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { apiCredentialMessages } from '@/i18n/apiCredentialMessages'
import { getAccessToken } from '@/auth/tokenStorage'
import CredentialStatisticsDialog from '@/components/integrations/CredentialStatisticsDialog.vue'
import ServiceIdentityPanel from '@/components/integrations/ServiceIdentityPanel.vue'

registerUiMessages(apiCredentialMessages)

const auth = useAuthStore()
const rows = ref<APICredential[]>([]), scopes = ref<{ code: string; label: string }[]>([])
const page = ref(1), pageSize = ref(10), total = ref(0), days = ref(30)
const draft = ref({ name: '', scopes: [] as string[] })
const loading = ref(false), busy = ref(false), error = ref(''), confirmationOpen = ref(false)
const operation = ref<'create' | 'revoke' | 'rotate'>('create'), target = ref<APICredential | null>(null)
const statisticsTarget = ref<APICredential | null>(null)
const confirmationDescription = computed(() => uiText(operation.value === 'create'
  ? '确认创建本人只读开放凭证？密钥只展示一次。' : operation.value === 'rotate'
    ? '确认轮换所选密钥？旧密钥立即失效，权限和到期时间保持不变。新密钥仅展示一次。'
    : '确认撤销所选开放凭证？撤销后不能恢复。'))
const secretOpen = ref(false), issuedSecret = ref('')
const canCreate = computed(() => auth.can('api_credential:create')), canRevoke = computed(() => auth.can('api_credential:revoke'))
const validDraft = computed(() => !!draft.value.name.trim() && draft.value.scopes.length > 0 && days.value >= 1 && days.value <= 90)
const time = (value: string | null) => value ? formatDateTime(value) : '—'
const columns = computed(() => [
  { prop: 'name', label: uiText('名称'), width: 180 },
  { prop: 'scopes', label: uiText('只读能力'), width: 220, render: (value: string[]) => value.join(', ') },
  { prop: 'expires_at', label: uiText('过期时间'), width: 220, render: time },
  { prop: 'last_used_at', label: uiText('最近使用'), width: 220, render: time },
  { prop: 'revoked_at', label: uiText('撤销时间'), width: 220, render: time },
  { prop: 'version', label: uiText('密钥版本'), width: 100 },
  { prop: 'accepted_requests', label: uiText('已授权请求'), width: 120 },
])
let alive = true, controller: AbortController | undefined
function clearSecret() { issuedSecret.value = ''; secretOpen.value = false }
async function load() {
  if (busy.value) return
  controller?.abort(); const active = controller = new AbortController()
  loading.value = true; error.value = ''; rows.value = []; total.value = 0
  try {
    const [result, choices] = await Promise.all([apiCredentialsApi.list(page.value, pageSize.value, active.signal), canCreate.value ? apiCredentialsApi.scopes(active.signal) : Promise.resolve([])])
    if (!alive || controller !== active) return
    rows.value = result.items; total.value = result.pagination.total; scopes.value = choices
  } catch { if (alive && !active.signal.aborted) error.value = uiText('开放凭证加载失败，请刷新重试。') }
  finally { if (alive && controller === active) loading.value = false }
}
function changePage(value: number) { if (!busy.value) { page.value = value; void load() } }
function changeSize(value: number) { if (!busy.value) { pageSize.value = value; page.value = 1; void load() } }
function prepareCreate() { if (!canCreate.value || !validDraft.value || busy.value || loading.value) return; clearSecret(); operation.value = 'create'; confirmationOpen.value = true }
function prepareRevoke(row: APICredential) { if (!canRevoke.value || busy.value || loading.value || row.revoked_at) return; operation.value = 'revoke'; target.value = row; confirmationOpen.value = true }
function prepareRotate(row: APICredential) {
  if (!canCreate.value || !canRevoke.value || busy.value || loading.value || row.revoked_at || new Date(row.expires_at).getTime() <= Date.now()) return
  clearSecret(); operation.value = 'rotate'; target.value = row; confirmationOpen.value = true
}
async function execute(password: string) {
  const startingToken = getAccessToken()
  if (operation.value === 'create') {
    if (!canCreate.value || !validDraft.value) throw new Error('permission changed')
    const data = await apiCredentialsApi.create({ ...draft.value, scopes: [...draft.value.scopes], expires_at: new Date(Date.now() + days.value * 86400000).toISOString() }, password)
    if (!alive || !canCreate.value || !tokensBelongToSameSession(startingToken, getAccessToken())) return
    issuedSecret.value = data.token; secretOpen.value = true; draft.value = { name: '', scopes: [] }
  } else if (operation.value === 'rotate') {
    if (!canCreate.value || !canRevoke.value || !target.value) throw new Error('permission changed')
    const data = await apiCredentialsApi.rotate(target.value.id, target.value.version, password)
    if (!alive || !canCreate.value || !canRevoke.value || !tokensBelongToSameSession(startingToken, getAccessToken())) return
    issuedSecret.value = data.token; secretOpen.value = true
  } else {
    if (!canRevoke.value || !target.value) throw new Error('permission changed')
    await apiCredentialsApi.revoke(target.value.id, password)
  }
}
watch(confirmationOpen, value => { if (!value) { target.value = null; if (alive) void load() } })
watch(secretOpen, value => { if (!value) issuedSecret.value = '' })
watch(() => auth.user?.id, () => { clearSecret(); statisticsTarget.value = null; draft.value = { name: '', scopes: [] }; confirmationOpen.value = false; controller?.abort(); rows.value = []; scopes.value = []; total.value = 0 })
watch(canCreate, value => { if (!value) { clearSecret(); draft.value = { name: '', scopes: [] }; if (!busy.value) confirmationOpen.value = false } })
watch(canRevoke, value => { if (!value && operation.value !== 'create') { clearSecret(); if (!busy.value) confirmationOpen.value = false } })
watch(() => auth.can('api_credential:read'), value => { if (!value) statisticsTarget.value = null })
void load()
onBeforeRouteLeave(() => { clearSecret(); draft.value = { name: '', scopes: [] } })
onBeforeUnmount(() => { alive = false; controller?.abort(); clearSecret(); draft.value = { name: '', scopes: [] } })
</script>

<style scoped>
.credentials-page { display: grid; gap: var(--spacing-lg); min-width: 0; }
.heading { display: flex; justify-content: space-between; gap: var(--spacing-md); }
.heading > div { min-width: 0; }
h1 { margin: 0 0 var(--spacing-sm); font-size: var(--font-size-xl); }
p { line-height: 1.6; overflow-wrap: anywhere; }
.heading p { color: var(--color-text-secondary); }
.el-form { max-width: 600px; }
textarea { display: block; box-sizing: border-box; width: 100%; margin-top: var(--spacing-sm); padding: var(--spacing-sm); border: 1px solid var(--color-border); background: var(--color-bg-card); color: var(--color-text-primary); overflow-wrap: anywhere; resize: vertical; }
code { overflow-wrap: anywhere; }
@media (max-width: 768px) { .heading { flex-wrap: wrap; } }
</style>
