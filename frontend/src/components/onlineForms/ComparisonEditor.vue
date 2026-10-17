<template>
  <div class="comparisons">
    <div v-for="(rule, index) in modelValue" :key="index" class="comparison">
      <el-select v-model="rule.left" :aria-label="uiText('左侧字段')"
        ><el-option
          v-for="field in comparable"
          :key="field.key"
          :label="field.label"
          :value="field.key"
      /></el-select>
      <el-select v-model="rule.op" :aria-label="uiText('比较操作')"
        ><el-option
          v-for="op in ['lt', 'lte', 'gt', 'gte', 'eq']"
          :key="op"
          :label="symbols[op]"
          :value="op"
      /></el-select>
      <el-select v-model="rule.right" :aria-label="uiText('右侧字段')"
        ><el-option
          v-for="field in comparable.filter(
            (f) =>
              f.key !== rule.left &&
              f.type === fields.find((x) => x.key === rule.left)?.type,
          )"
          :key="field.key"
          :label="field.label"
          :value="field.key"
      /></el-select>
      <el-input
        v-model="rule.message"
        :aria-label="uiText('校验失败提示')"
        :maxlength="200"
      />
      <el-button
        :aria-label="uiText('删除校验')"
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
      :disabled="comparable.length < 2 || modelValue.length >= 20"
      @click="add"
      >{{ uiText("添加跨字段校验") }}</el-button
    >
  </div>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { OnlineFormField, OnlineFormRule } from "@/api";
import { uiText } from "@/i18n/uiText";
const props = defineProps<{
  modelValue: OnlineFormRule[];
  fields: OnlineFormField[];
}>();
const emit = defineEmits<{ "update:modelValue": [value: OnlineFormRule[]] }>();
const comparable = computed(() =>
  props.fields.filter((f) =>
    ["number", "decimal", "date", "datetime"].includes(f.type),
  ),
);
const symbols: Record<string, string> = {
  lt: "<",
  lte: "≤",
  gt: ">",
  gte: "≥",
  eq: "=",
};
function add() {
  const left = comparable.value[0];
  if (left)
    emit("update:modelValue", [
      ...props.modelValue,
      {
        left: left.key,
        op: "lte",
        right:
          comparable.value.find(
            (f) => f.key !== left.key && f.type === left.type,
          )?.key || "",
        message: uiText("字段比较校验失败"),
      },
    ]);
}
</script>
<style scoped>
.comparisons {
  display: grid;
  gap: 10px;
}
.comparison {
  display: grid;
  grid-template-columns:
    minmax(90px, 1fr) 75px minmax(90px, 1fr) minmax(140px, 2fr)
    auto;
  gap: 8px;
}
@media (max-width: 900px) {
  .comparison {
    grid-template-columns: minmax(0, 1fr);
  }
  .comparison button {
    min-height: 44px;
  }
}
</style>
