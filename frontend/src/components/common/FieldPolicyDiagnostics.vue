<template>
  <el-dialog :model-value="visible && allowed" :title="uiText('字段权限诊断')" width="min(700px, 94vw)" append-to-body @close="emit('close')">
    <p class="diagnostic-note">{{ uiText('诊断当前已保存的策略，不读取业务值。字段放行仍需通过记录范围、附件 ACL、表单只读状态和业务校验。') }}</p>
    <el-form label-position="top" @submit.prevent="load">
      <el-form-item :label="uiText('目标用户 ID')"><el-input v-model="form.user_id" :aria-label="uiText('目标用户 ID')" /></el-form-item>
      <div class="diagnostic-inputs">
        <el-form-item :label="uiText('资源')"><el-select v-model="form.resource" :aria-label="uiText('资源')" filterable><el-option v-for="resource in Object.keys(resources)" :key="resource" :label="resource" :value="resource" /></el-select></el-form-item>
        <el-form-item :label="uiText('字段')"><el-select v-model="form.field" :aria-label="uiText('字段')" filterable><el-option v-for="field in resources[form.resource] || []" :key="field" :label="field" :value="field" /></el-select></el-form-item>
        <el-form-item :label="uiText('操作')"><el-select v-model="form.operation" :aria-label="uiText('操作')"><el-option v-for="item in operations" :key="item.value" :label="uiText(item.label)" :value="item.value" /></el-select></el-form-item>
      </div>
      <el-button native-type="submit" type="primary" :loading="loading" :disabled="!validInput">{{ uiText('运行诊断') }}</el-button>
    </el-form>
    <div v-if="loading" role="status" class="diagnostic-output">{{ uiText('正在读取当前权限…') }}</div>
    <el-alert v-else-if="error" class="diagnostic-output" :title="error" type="error" :closable="false" />
    <section v-else-if="result" class="diagnostic-output" aria-live="polite">
      <p>{{ uiText('字段策略') }}: <strong>{{ uiText(result.field_allowed ? '允许' : '拒绝') }}</strong> · {{ uiText(reasons[result.field_reason]) }}</p>
      <p>{{ uiText('功能权限检查') }}: <strong>{{ uiText(result.operation_allowed ? '允许' : '拒绝') }}</strong> · {{ result.permission_code || uiText('没有此操作入口') }}</p>
      <p v-if="!result.module_enabled">{{ uiText('该模块已关闭') }}</p>
      <p v-if="!result.user_active">{{ uiText('用户已停用') }}</p>
      <p v-if="result.must_change_password">{{ uiText('用户必须先修改密码') }}</p>
      <p v-if="result.requires_admin">{{ uiText('该操作还要求管理员身份') }}</p>
      <p class="diagnostic-note">{{ uiText('未评估具体记录是否可访问；本结果不是写入授权。只读字段、创建者限制及敏感原值二次验证仍由业务入口执行。') }}</p>
      <ul v-if="result.roles.length" class="diagnostic-roles">
        <li v-for="role in result.roles" :key="role.id">
          <strong>{{ role.name }}</strong> (v{{ role.version }}) · {{ uiText(role.active ? '激活' : '停用') }}
          · {{ uiText(role.declared ? '已声明字段限制' : '未声明字段限制') }}
          · {{ uiText('字段来源') }}: {{ uiText(role.field_granted ? '允许' : '无贡献') }}
          · {{ uiText('功能来源') }}: {{ uiText(role.operation_granted ? '允许' : '无贡献') }}
        </li>
      </ul>
      <p v-else>{{ uiText('没有分配角色') }}</p>
      <div v-if="result.data_scope.length">
        <p>{{ uiText('记录范围策略（有效角色按并集合并）') }}</p>
        <ul><li v-for="grant in result.data_scope" :key="grant.role_id">{{ roleName(grant.role_id) }} · {{ uiText(grant.active ? '激活' : '停用') }} · {{ uiText(scopes[grant.scope] || grant.scope) }}</li></ul>
      </div>
      <p v-else>{{ uiText('未配置范围策略；仍需遵守该业务入口的默认范围与 ACL。') }}</p>
    </section>
    <template #footer><el-button @click="emit('close')">{{ uiText('关闭') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { registerUiMessages, uiText } from '@/i18n/uiText'
import { diagnoseField, type FieldDiagnosticInput, type FieldDiagnosticResult } from '@/api/fieldDiagnostics'
import { responseStatus } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'

registerUiMessages({
  '字段权限诊断': 'Field permission diagnostics', '目标用户 ID': 'Target user ID', '资源': 'Resource', '字段': 'Field', '操作': 'Operation',
  '运行诊断': 'Run diagnostics', '正在读取当前权限…': 'Reading current permissions…', '字段策略': 'Field policy', '功能权限检查': 'Operation permission check',
  '读取': 'Read', '新增': 'Create', '修改': 'Update',
  '允许': 'Allowed', '拒绝': 'Denied', '没有此操作入口': 'This operation is unavailable', '该模块已关闭': 'This module is disabled',
  '用户已停用': 'The user is inactive', '用户必须先修改密码': 'The user must change their password first', '该操作还要求管理员身份': 'This operation also requires administrator status',
  '管理员绕过字段限制': 'Administrator bypasses field restrictions', '没有有效角色声明此资源限制，沿用完整登记字段': 'No active role declares restrictions for this resource; all registered fields remain available',
  '已声明策略按有效角色字段并集合并': 'Declared policies use the union of fields from active roles', '已声明字段限制': 'Field restrictions declared', '未声明字段限制': 'No field restrictions declared',
  '字段来源': 'Field contribution', '功能来源': 'Operation contribution', '无贡献': 'No contribution', '没有分配角色': 'No assigned roles',
  '记录范围策略（有效角色按并集合并）': 'Record scope policies (union of active roles)', '全部记录': 'All records', '本人记录': 'Own records', '本部门': 'Own department', '部门及下级': 'Department and descendants', '指定部门': 'Selected departments',
  '未配置范围策略；仍需遵守该业务入口的默认范围与 ACL。': 'No scope policy is configured; the business endpoint still enforces its default scope and ACL.',
  '诊断当前已保存的策略，不读取业务值。字段放行仍需通过记录范围、附件 ACL、表单只读状态和业务校验。': 'Diagnoses currently saved policies without reading business values. Field allowance still requires record scope, attachment ACL, form state, and business validation.',
  '未评估具体记录是否可访问；本结果不是写入授权。只读字段、创建者限制及敏感原值二次验证仍由业务入口执行。': 'Access to individual records is not evaluated. This result does not authorize writes. Business endpoints still enforce read-only fields, creator restrictions, and verification for sensitive values.',
  '无法诊断，请检查用户 ID 和当前租户后重试': 'Cannot diagnose. Check the user ID and current tenant, then retry.',
  '诊断失败，输入已保留，可重新运行': 'Diagnostics failed. Your input is preserved; run again to retry.',
})
const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const allowed = computed(() => !!(auth.user?.is_staff || auth.user?.is_superuser) && auth.can('role:read') && auth.can('user:read') && !auth.user?.must_change_password)
const resources = computed(() => modules.config?.field_policy_resources || {})
const owner = computed(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, auth.user?.must_change_password, tenants.currentId, modules.config]))
const form = reactive<FieldDiagnosticInput>({ user_id: '', resource: '', field: '', operation: 'read' })
const validInput = computed(() => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(form.user_id) && (resources.value[form.resource] || []).includes(form.field))
const operations = [{ value: 'read', label: '读取' }, { value: 'create', label: '新增' }, { value: 'update', label: '修改' }]
const reasons = { administrator: '管理员绕过字段限制', legacy_unrestricted: '没有有效角色声明此资源限制，沿用完整登记字段', explicit_union: '已声明策略按有效角色字段并集合并' }
const scopes: Record<string, string> = { all: '全部记录', self: '本人记录', department: '本部门', department_tree: '部门及下级', custom: '指定部门' }
const result = ref<FieldDiagnosticResult | null>(null), loading = ref(false), error = ref('')
let controller: AbortController | undefined, generation = 0
function reset() { generation++; controller?.abort(); result.value = null; error.value = ''; loading.value = false }
function roleName(identifier: string) { return result.value?.roles.find(role => role.id === identifier)?.name || identifier }
async function load() {
  reset()
  if (!allowed.value || !props.visible || !validInput.value) return
  const tick = generation, identity = owner.value, input = { ...form }
  controller = new AbortController(); loading.value = true
  const current = () => tick === generation && identity === owner.value && props.visible && allowed.value
  try { const data = await diagnoseField(input, controller.signal); if (current()) result.value = data }
  catch (failure) { if (current()) error.value = uiText([400, 403, 404].includes(responseStatus(failure) || 0) ? '无法诊断，请检查用户 ID 和当前租户后重试' : '诊断失败，输入已保留，可重新运行') }
  finally { if (current()) loading.value = false }
}
watch(() => form.resource, () => { form.field = resources.value[form.resource]?.[0] || '' }, { flush: 'sync' })
watch(form, reset, { flush: 'sync' })
watch(() => props.visible, visible => { reset(); if (visible) Object.assign(form, { user_id: auth.user?.id || '', resource: Object.keys(resources.value)[0] || '', operation: 'read' }) }, { immediate: true })
watch(owner, () => { reset(); Object.assign(form, { user_id: '', resource: '', field: '', operation: 'read' }); if (props.visible) emit('close') }, { flush: 'sync' })
onBeforeUnmount(reset)
</script>

<style scoped>
.diagnostic-note { color: var(--el-text-color-secondary); font-size: 13px; overflow-wrap: anywhere; }
.diagnostic-inputs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.diagnostic-inputs .el-select { width: 100%; }
.diagnostic-output { margin-top: 16px; overflow-wrap: anywhere; }
.diagnostic-roles { padding-left: 20px; }
.diagnostic-roles li { margin: 8px 0; }
@media (max-width: 540px) { .diagnostic-inputs { grid-template-columns: 1fr; gap: 0; } }
</style>
