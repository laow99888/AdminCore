<template>
  <div class="conditions">
    <div v-for="(rule, index) in modelValue" :key="index" class="condition">
      <el-select
        :model-value="rule.field"
        :aria-label="uiText('条件字段')"
        @update:model-value="change(index, { field: $event, op: 'not_empty' })"
        ><el-option
          v-for="field in sources"
          :key="field.key"
          :label="field.label"
          :value="field.key"
      /></el-select>
      <el-select
        :model-value="rule.op"
        :aria-label="uiText('条件操作')"
        @update:model-value="changeOp(index, $event)"
        ><el-option
          v-for="op in ops.filter(
            (o) =>
              !['lt', 'lte', 'gt', 'gte'].includes(o.value) ||
              ['number', 'decimal', 'date', 'datetime'].includes(
                source(rule.field)?.type || '',
              ),
          )"
          :key="op.value"
          :label="uiText(op.label)"
          :value="op.value"
      /></el-select>
      <el-select
        v-if="rule.op === 'in'"
        :model-value="Array.isArray(rule.value) ? rule.value.map(String) : []"
        multiple
        filterable
        allow-create
        default-first-option
        :aria-label="uiText('条件候选值')"
        @update:model-value="
          change(index, {
            ...rule,
            value: $event.map((v: string) =>
              source(rule.field)?.type === 'number'
                ? Number(v)
                : source(rule.field)?.type === 'boolean'
                  ? v === 'true'
                  : v,
            ),
          })
        "
        ><el-option
          v-for="option in source(rule.field)?.type === 'boolean'
            ? ['true', 'false']
            : source(rule.field)?.options || []"
          :key="option"
          :label="option"
          :value="option"
      /></el-select>
      <OnlineFieldInput
        v-else-if="
          !['empty', 'not_empty'].includes(rule.op) && source(rule.field)
        "
        :id="`${uid}-${id}-${index}`"
        :field="{
          ...source(rule.field)!,
          label: uiText('条件值：{p0}', { p0: source(rule.field)!.label }),
        }"
        :model-value="rule.value"
        @update:model-value="change(index, { ...rule, value: $event })"
      />
      <el-button
        :aria-label="uiText('删除条件')"
        @click="
          emit(
            'update:modelValue',
            modelValue.filter((_r, i) => i !== index),
          )
        "
        >{{ uiText("删除") }}</el-button
      >
    </div>
    <el-button
      size="small"
      :disabled="!sources.length || modelValue.length >= 5"
      @click="add"
      >{{ uiText("添加条件（全部满足）") }}</el-button
    >
    <small>{{
      uiText("条件只引用前面的普通字段；调序或改名后请重新校验")
    }}</small>
  </div>
</template>
<script setup lang="ts">
import type { OnlineFormCondition, OnlineFormField } from "@/api";
import { computed, useId } from "vue";
import { uiText } from "@/i18n/uiText";
import OnlineFieldInput from "./OnlineFieldInput.vue";
const props = defineProps<{
  modelValue: OnlineFormCondition[];
  fields: OnlineFormField[];
  id: string;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: OnlineFormCondition[]];
}>();
const uid = useId();
const sources = computed(() =>
  props.fields.filter((f) => !["detail", "multiselect"].includes(f.type)),
);
const ops = [
  { value: "eq", label: "等于" },
  { value: "ne", label: "不等于" },
  { value: "in", label: "属于候选值" },
  { value: "lt", label: "小于" },
  { value: "lte", label: "小于等于" },
  { value: "gt", label: "大于" },
  { value: "gte", label: "大于等于" },
  { value: "empty", label: "为空" },
  { value: "not_empty", label: "不为空" },
];
function source(key: string) {
  return sources.value.find((f) => f.key === key);
}
function change(index: number, rule: OnlineFormCondition) {
  emit(
    "update:modelValue",
    props.modelValue.map((r, i) => (i === index ? rule : r)),
  );
}
function changeOp(index: number, op: OnlineFormCondition["op"]) {
  const rule = props.modelValue[index]!;
  change(index, {
    field: rule.field,
    op,
    ...(!["empty", "not_empty"].includes(op)
      ? {
          value:
            op === "in"
              ? []
              : (source(rule.field)?.default ??
                (source(rule.field)?.type === "boolean" ? false : undefined)),
        }
      : {}),
  });
}
function add() {
  const field = sources.value[0];
  if (field)
    emit("update:modelValue", [
      ...props.modelValue,
      { field: field.key, op: "not_empty" },
    ]);
}
</script>
<style scoped>
.conditions {
  display: grid;
  gap: 8px;
  width: 100%;
}
.condition {
  display: grid;
  grid-template-columns:
    minmax(100px, 1fr) minmax(100px, 1fr) minmax(100px, 1fr)
    auto;
  gap: 8px;
}
.conditions small {
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
@media (max-width: 900px) {
  .condition {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  .condition button {
    min-height: 44px;
  }
}
</style>
