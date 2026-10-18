<template>
  <div class="relation-input">
    <el-select v-if="!formDisabled" :id="id" :aria-label="label" :model-value="modelValue || undefined"
      :disabled="!context" filterable remote clearable :loading="loading" :remote-method="search"
      @visible-change="(value: boolean) => { if (value) search('') }" @update:model-value="emit('update:modelValue', $event || undefined)">
      <!-- 远程 select 不监听现存选项标签；授权解析或撤权后须重新登记，清除缓存摘要。 -->
      <el-option v-for="item in options" :key="`${item.id}:${item.title}`" :value="item.id" :label="item.title" />
      <el-option v-if="modelValue && !options.some(item => item.id === modelValue)" :key="`${modelValue}:${selected?.title || ''}`" :value="String(modelValue)"
        :label="selected?.title || uiText('关联记录不可用或无权访问')" />
    </el-select>
    <span v-else-if="selected">{{ selected.title }}</span>
    <span v-else-if="modelValue">{{ uiText('关联记录不可用或无权访问') }}</span>
    <span v-else>{{ uiText('未选择关联记录') }}</span>
    <el-button v-if="more && !formDisabled" :disabled="loading" @click="loadMore">{{ uiText('加载更多') }}</el-button>
    <small v-if="!context">{{ uiText('保存表单后可选择关联记录；新增关联字段请先保存') }}</small>
    <small v-else-if="!formDisabled">{{ uiText('仅显示当前租户和权限范围内的业务记录') }}</small>
    <p v-if="failure" role="alert">{{ failure }} <el-button :disabled="loading" link @click="load(formDisabled)">{{ uiText('重试') }}</el-button></p>
  </div>
</template>
<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './relationMessages'
import { onBeforeUnmount, ref, watch } from 'vue'
import { useFormDisabled } from 'element-plus'
import { errorMessage } from '@/api/request'
import type { OnlineAttachmentContext } from '@/api/onlineFormAttachments'
import { onlineFormRelationsApi, type OnlineRelation } from '@/api/onlineFormRelations'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { uiText } from '@/i18n/uiText'

const props = defineProps<{ id: string; label: string; modelValue?: unknown; context?: OnlineAttachmentContext; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const auth = useAuthStore(), tenants = useTenantStore(), formDisabled = useFormDisabled()
const options = ref<OnlineRelation[]>([]), selected = ref<OnlineRelation | null>(null)
const loading = ref(false), more = ref(false), failure = ref('')
let generation = 0, controller: AbortController | undefined, page = 1, query = ''
function reset() {
  generation++; controller?.abort(); options.value = []; selected.value = null
  loading.value = false; more.value = false; failure.value = ''; page = 1; query = ''
}
async function load(resolve = false, append = false) {
  const context = props.context
  if (!context || (!resolve && formDisabled.value)) return
  const current = ++generation
  controller?.abort(); controller = new AbortController(); loading.value = true; failure.value = ''
  try {
    const result = await onlineFormRelationsApi.choices(context, props.id, {
      selected: typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : undefined, q: query, page, resolve,
    }, controller.signal)
    if (current !== generation) return
    selected.value = result.selected
    if (!resolve) { options.value = append ? [...options.value, ...result.items] : result.items; more.value = result.has_more }
  } catch (err) {
    if (current === generation) { selected.value = null; failure.value = errorMessage(err, uiText('关联记录加载失败，请重试')); if (append) page-- }
  } finally { if (current === generation) loading.value = false }
}
function search(value: string) { query = value; page = 1; void load() }
function loadMore() { if (!loading.value) { page++; void load(false, true) } }
watch(() => JSON.stringify([JSON.stringify(props.context), props.id, props.modelValue, auth.user?.id, sessionIdentity(auth.token),
  JSON.stringify(auth.user?.permissions), tenants.currentId]), () => { reset(); if (props.modelValue) void load(true) }, { immediate: true, flush: 'sync' })
watch(formDisabled, () => { reset(); if (props.modelValue) void load(true) }, { flush: 'sync' })
onBeforeUnmount(reset)
</script>
<style scoped>
.relation-input { display: grid; gap: 6px; width: 100%; min-width: 0; overflow-wrap: anywhere; }
small { color: var(--el-text-color-secondary); line-height: 1.6; }
p { color: var(--el-color-danger); margin: 0; }
</style>
