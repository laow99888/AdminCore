<template>
  <el-input
    v-if="['string', 'text', 'decimal'].includes(field.kind)"
    :model-value="String(modelValue ?? '')"
    :type="
      field.kind === 'text' || field.component === 'textarea'
        ? 'textarea'
        : 'text'
    "
    :inputmode="field.kind === 'decimal' ? 'decimal' : undefined"
    :maxlength="field.max_length"
    :aria-label="label" :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <el-input-number
    v-else-if="field.kind === 'integer'"
    :model-value="typeof modelValue === 'number' ? modelValue : undefined"
    :min="Number(field.minimum ?? -2147483648)"
    :max="Number(field.maximum ?? 2147483647)"
    :precision="0"
    :aria-label="label" :disabled="disabled"
    @update:model-value="
      emit('update:modelValue', $event === '' || $event == null ? null : $event)
    "
  />
  <el-switch
    v-else-if="field.kind === 'boolean' && field.component !== 'select'"
    :model-value="modelValue === true"
    :aria-label="label" :disabled="disabled"
    @update:model-value="emit('update:modelValue', Boolean($event))"
  />
  <el-select
    v-else-if="field.kind === 'boolean'"
    :model-value="modelValue"
    :aria-label="label" :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
    ><el-option :label="uiText('是')" :value="true" /><el-option
      :label="uiText('否')"
      :value="false"
  /></el-select>
  <el-date-picker
    v-else-if="field.kind === 'date' || field.kind === 'datetime'"
    :model-value="typeof modelValue === 'string' ? modelValue : null"
    :type="field.kind === 'date' ? 'date' : 'datetime'"
    :value-format="
      field.kind === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm:ssZ'
    "
    :aria-label="label" :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event || null)"
  />
  <el-radio-group
    v-else-if="field.kind === 'enum' && field.component === 'radio'"
    :model-value="modelValue ?? ''"
    :aria-label="label" :disabled="disabled"
    @update:model-value="emit('update:modelValue', String($event))"
    ><el-radio
      v-for="item in field.choices"
      :key="item.value"
      :value="item.value"
      >{{ uiText(item.label) }}</el-radio
    ></el-radio-group
  >
  <div v-else class="remote-field">
    <el-select
      :model-value="modelValue"
      :aria-label="label" :disabled="disabled"
      :loading="loading"
      filterable
      :remote="remote"
      :remote-method="search"
      :clearable="!field.required && field.kind !== 'enum'"
      @visible-change="open"
      @update:model-value="
        emit(
          'update:modelValue',
          $event === '' || $event == null
            ? field.kind === 'dictionary'
              ? ''
              : null
            : $event,
        )
      "
    >
      <el-option
        v-for="item in choices"
        :key="item.value"
        :label="field.kind === 'enum' ? uiText(item.label) : item.label"
        :value="item.value"
      />
    </el-select>
    <span v-if="failure" role="alert"
      >{{ uiText("选项加载失败，请重试") }}
      <el-button link @click="search(query)">{{
        uiText("重试")
      }}</el-button></span
    >
    <el-button v-if="hasMore" link :disabled="loading" @click="loadMore">{{
      uiText("加载更多")
    }}</el-button>
    <small v-if="field.kind === 'file'">{{
      uiText("选择已上传且有权访问的文件")
    }}</small>
  </div>
</template>
<script setup lang="ts">
import "./messages";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import request, { type ApiResponse } from "@/api/request";
import { useAuthStore } from "@/stores/auth";
import { uiText } from "@/i18n/uiText";
import type { Choice, FieldValue, GeneratedField } from "./types";
const props = defineProps<{
  field: GeneratedField;
  modelValue?: FieldValue;
  endpoint: string;
  fieldKey: string;
  label: string;
  selectedLabel?: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: FieldValue] }>();
const auth = useAuthStore(),
  options = ref<Choice[]>([]),
  loading = ref(false),
  failure = ref(false),
  hasMore = ref(false);
const remote = computed(() =>
  ["relation", "file", "dictionary"].includes(props.field.kind),
);
const choices = computed(() => {
  if (props.field.kind === "enum") return props.field.choices ?? [];
  const current = props.modelValue;
  return current && !options.value.some((item) => item.value === current)
    ? [
        {
          value: String(current),
          label: props.selectedLabel || String(current),
        },
        ...options.value,
      ]
    : options.value;
});
let generation = 0,
  page = 1,
  query = "",
  controller: AbortController | undefined;
async function load(append = false) {
  if (props.disabled) return;
  const current = ++generation;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  failure.value = false;
  try {
    const response = await request.get<
      ApiResponse<{ items: Choice[]; has_more: boolean }>
    >(props.endpoint + "choices/", {
      params: { field: props.fieldKey, q: query, page },
      signal: controller.signal,
    });
    if (current !== generation) return;
    options.value = append
      ? [...options.value, ...response.data.data.items]
      : response.data.data.items;
    hasMore.value = response.data.data.has_more;
  } catch {
    if (current === generation) {
      failure.value = true;
      if (append) page--;
    }
  } finally {
    if (current === generation) loading.value = false;
  }
}
function search(value: string) {
  query = value;
  page = 1;
  void load();
}
function loadMore() {
  if (!loading.value) {
    page++;
    void load(true);
  }
}
function open(value: boolean) {
  if (value && remote.value) search(query);
}
function reset() {
  generation++;
  controller?.abort();
  options.value = [];
  failure.value = false;
  hasMore.value = false;
  loading.value = false;
  page = 1;
  query = "";
}
watch(
  () => [
    props.endpoint,
    props.fieldKey,
    auth.user?.id,
    auth.token,
    JSON.stringify(auth.user?.permissions),
  ],
  reset,
);
onBeforeUnmount(reset);
</script>
<style scoped>
.remote-field {
  display: grid;
  gap: 4px;
  width: 100%;
}
.remote-field span {
  color: var(--el-color-danger);
}
small {
  color: var(--el-text-color-secondary);
}
:deep(.el-select),
:deep(.el-date-editor) {
  width: 100%;
}
</style>
