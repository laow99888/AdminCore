<template>
  <AppLayout>
    <section class="identities-page">
      <div class="heading"><div><h1>{{ uiText('企业身份绑定') }}</h1><p>{{ uiText('仅管理员可把供应商的固定 subject 显式绑定到已有本地账号。不会自动创建用户、匹配邮箱或授予角色。') }}</p></div><BaseButton variant="ghost" :disabled="busy || loading" :loading="loading" @click="load">{{ uiText('刷新') }}</BaseButton></div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert :title="uiText('请从供应商管理台核对不可变的 subject 与本地用户 UUID；本地密码和双因素认证继续有效。撤销绑定立即终止对应企业会话。')" type="info" :closable="false" show-icon />
      <el-card v-if="canBind" shadow="never">
        <template #header>{{ uiText('绑定已有本地账号') }}</template>
        <el-form label-position="top" @submit.prevent="prepareBind">
          <el-form-item :label="uiText('本地用户 UUID')"><el-input v-model.trim="userId" :aria-label="uiText('本地用户 UUID')" maxlength="36" :disabled="busy || loading" /></el-form-item>
          <el-form-item :label="uiText('供应商 subject')"><el-input v-model="subject" :aria-label="uiText('供应商 subject')" maxlength="255" :disabled="busy || loading" /></el-form-item>
          <BaseButton native-type="submit" :disabled="!validDraft || busy || loading">{{ uiText('确认绑定') }}</BaseButton>
        </el-form>
      </el-card>
      <p v-if="loading" role="status">{{ uiText('正在加载企业身份绑定') }}</p>
      <BaseTable :data="rows" :columns="columns" :loading="loading" :total="total" :current-page="page" :page-size="pageSize" :show-index="false" :show-actions="canUnbind" :action-width="140" @update:current-page="changePage" @update:page-size="changeSize">
        <template #actions="{ row }"><BaseButton variant="ghost" :disabled="busy || loading || !!row.revoked_at" @click="prepareUnbind(row)">{{ uiText('撤销企业绑定') }}</BaseButton></template>
      </BaseTable>
      <PasswordConfirmationDialog v-model="confirmationOpen" :description="uiText(operation === 'bind' ? '确认将此企业 subject 绑定到指定本地用户？请先核对双方身份。' : '确认撤销企业身份绑定并终止对应企业会话？本地登录仍可使用。')" :confirm-text="uiText(operation === 'bind' ? '确认绑定' : '撤销企业绑定')" :execute="execute" :disabled="operation === 'bind' ? !canBind || !validDraft : !canUnbind || !target" :error-text="uiText('绑定操作未确认，请检查密码、账号状态和重复绑定后重试。')" @busy="busy = $event" />
    </section>
  </AppLayout>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseTable } from '@/components'
import PasswordConfirmationDialog from '@/components/auth/PasswordConfirmationDialog.vue'
import { ssoApi, type ExternalIdentity } from '@/api/sso'
import { useAuthStore } from '@/stores/auth'
import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { ssoMessages } from '@/i18n/ssoMessages'
import { getAccessToken } from '@/auth/tokenStorage'
registerUiMessages(ssoMessages)
const auth = useAuthStore(), rows = ref<ExternalIdentity[]>([]), userId = ref(''), subject = ref('')
const page = ref(1), pageSize = ref(10), total = ref(0), loading = ref(false), busy = ref(false), error = ref(''), confirmationOpen = ref(false)
const operation = ref<'bind' | 'unbind'>('bind'), target = ref<ExternalIdentity | null>(null)
const administrator = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser))
const canBind = computed(() => administrator.value && auth.can('sso:bind')), canUnbind = computed(() => administrator.value && auth.can('sso:unbind'))
const validDraft = computed(() => /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(userId.value) && /^[\x21-\x7e]{1,255}$/.test(subject.value))
const columns = computed(() => [
  { prop: 'username', label: uiText('本地账号'), width: 160 }, { prop: 'user_id', label: uiText('本地用户 UUID'), width: 300 },
  { prop: 'issuer', label: uiText('身份签发方'), width: 260 }, { prop: 'subject', label: uiText('供应商 subject'), width: 240 },
  { prop: 'revoked_at', label: uiText('撤销时间'), width: 200, render: (value: string | null) => value ? new Date(value).toLocaleString() : '—' },
])
let controller: AbortController | undefined, alive = true
async function load() {
  if (busy.value) return
  controller?.abort(); const active = controller = new AbortController()
  loading.value = true; error.value = ''; rows.value = []; total.value = 0
  try { const result = await ssoApi.list(page.value, pageSize.value, active.signal); if (alive && controller === active) { rows.value = result.items; total.value = result.pagination.total } }
  catch { if (alive && !active.signal.aborted) error.value = uiText('企业身份绑定加载失败，请刷新重试。') }
  finally { if (alive && controller === active) loading.value = false }
}
function changePage(value: number) { if (!busy.value) { page.value = value; void load() } }
function changeSize(value: number) { if (!busy.value) { pageSize.value = value; page.value = 1; void load() } }
function prepareBind() { if (canBind.value && validDraft.value && !busy.value && !loading.value) { operation.value = 'bind'; confirmationOpen.value = true } }
function prepareUnbind(row: ExternalIdentity) { if (canUnbind.value && !row.revoked_at && !busy.value && !loading.value) { operation.value = 'unbind'; target.value = row; confirmationOpen.value = true } }
async function execute(password: string) {
  const startingToken = getAccessToken()
  if (operation.value === 'bind') {
    if (!canBind.value || !validDraft.value) throw new Error('permission changed')
    await ssoApi.bind(userId.value, subject.value, password)
    if (alive && tokensBelongToSameSession(startingToken, getAccessToken())) { userId.value = ''; subject.value = '' }
  } else {
    if (!canUnbind.value || !target.value) throw new Error('permission changed')
    await ssoApi.unbind(target.value.id, password)
  }
}
watch(confirmationOpen, value => { if (!value) { target.value = null; if (alive) void load() } })
watch(() => auth.user?.id, () => { controller?.abort(); rows.value = []; total.value = 0; userId.value = ''; subject.value = ''; confirmationOpen.value = false })
watch([canBind, canUnbind], () => { if (!busy.value) confirmationOpen.value = false })
void load()
onBeforeUnmount(() => { alive = false; controller?.abort(); userId.value = ''; subject.value = '' })
</script>
<style scoped>
.identities-page { display: grid; gap: var(--spacing-lg); min-width: 0; }
.heading { display: flex; justify-content: space-between; gap: var(--spacing-md); } .heading > div { min-width: 0; }
h1 { font-size: var(--font-size-xl); margin: 0 0 var(--spacing-sm); } p { line-height: 1.6; overflow-wrap: anywhere; color: var(--color-text-secondary); }
.el-form { max-width: 620px; }
@media (max-width: 768px) { .heading { flex-wrap: wrap; } }
</style>
