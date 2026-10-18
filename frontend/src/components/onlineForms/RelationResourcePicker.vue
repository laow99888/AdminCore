<template>
  <div class="resource-picker">
    <el-select :model-value="modelValue" :aria-label="uiText('关联资源')" :loading="loading" @update:model-value="emit('update:modelValue', $event)">
      <el-option v-for="resource in resources" :key="resource.code" :value="resource.code" :label="resource.title" />
      <el-option v-if="modelValue && !resources.some(item => item.code === modelValue)" :value="modelValue" :label="uiText('关联记录不可用或无权访问')" disabled />
    </el-select>
    <p v-if="failure" role="alert">{{ failure }} <el-button link @click="load">{{ uiText('重试') }}</el-button></p>
  </div>
</template>
<script setup lang="ts">
import './relationMessages'
import { onBeforeUnmount, ref, watch } from 'vue'
import { onlineFormRelationsApi } from '@/api/onlineFormRelations'
import { errorMessage } from '@/api/request'
import { uiText } from '@/i18n/uiText'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
defineProps<{ modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const auth = useAuthStore(), tenants = useTenantStore()
const resources = ref<{ code: string; title: string }[]>([]), loading = ref(false), failure = ref('')
let generation = 0, controller: AbortController | undefined
async function load() {
  const current = ++generation
  controller?.abort(); controller = new AbortController(); resources.value = []; failure.value = ''; loading.value = true
  try { const result = await onlineFormRelationsApi.resources(controller.signal); if (current === generation) resources.value = result }
  catch (err) { if (current === generation) failure.value = errorMessage(err, uiText('关联资源加载失败，请重试')) }
  finally { if (current === generation) loading.value = false }
}
watch(() => [auth.user?.id, auth.token, JSON.stringify(auth.user?.permissions), tenants.currentId], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>
<style scoped>
.resource-picker { width: 100%; min-width: 0; }
p { color: var(--el-color-danger); margin: 4px 0; }
</style>
