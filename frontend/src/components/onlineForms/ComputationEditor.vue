<template>
  <div class="computation">
    <el-form-item :label="uiText('金额来源')">
      <el-select
        :model-value="modelValue?.op || 'manual'"
        :aria-label="uiText('金额来源')"
        @update:model-value="changeOperation"
      >
        <el-option
          v-for="operation in operations"
          :key="operation.value"
          :label="uiText(operation.label)"
          :value="operation.value"
        />
      </el-select>
    </el-form-item>
    <template v-if="modelValue?.op === 'sum'">
      <el-form-item :label="uiText('汇总明细')">
        <el-select
          :model-value="modelValue.detail"
          :aria-label="uiText('汇总明细')"
          @update:model-value="changeDetail"
        >
          <el-option
            v-for="detail in details"
            :key="detail.key"
            :label="detail.label"
            :value="detail.key"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="uiText('汇总金额列')">
        <el-select
          :model-value="modelValue.field"
          :aria-label="uiText('汇总金额列')"
          @update:model-value="
            emit('update:modelValue', { ...modelValue, field: $event })
          "
        >
          <el-option
            v-for="field in detailColumns"
            :key="field.key"
            :label="field.label"
            :value="field.key"
          />
        </el-select>
      </el-form-item>
    </template>
    <div v-else-if="modelValue" class="operands">
      <div v-for="index in [0, 1]" :key="index">
        <el-form-item :label="uiText('第 {p0} 个计算来源', { p0: index + 1 })">
          <el-select
            :model-value="
              operand(index) && 'field' in operand(index)! ? 'field' : 'literal'
            "
            :aria-label="uiText('第 {p0} 个计算来源', { p0: index + 1 })"
            @update:model-value="
              setOperand(
                index,
                $event === 'field'
                  ? { field: sources[0]?.key || '' }
                  : { literal: '0' },
              )
            "
          >
            <el-option
              :label="uiText('金额字段')"
              value="field"
              :disabled="!sources.length"
            />
            <el-option :label="uiText('十进制常量')" value="literal" />
          </el-select>
        </el-form-item>
        <el-select
          v-if="'field' in operand(index)!"
          :model-value="sourceValue(index)"
          :aria-label="uiText('第 {p0} 个金额字段', { p0: index + 1 })"
          @update:model-value="setOperand(index, { field: $event })"
        >
          <el-option
            v-for="field in sources"
            :key="field.key"
            :label="field.label"
            :value="field.key"
          />
        </el-select>
        <el-input
          v-else
          :model-value="sourceValue(index)"
          :aria-label="uiText('第 {p0} 个十进制常量', { p0: index + 1 })"
          inputmode="decimal"
          :maxlength="28"
          @update:model-value="setOperand(index, { literal: $event })"
        />
      </div>
    </div>
    <p v-if="modelValue" class="hint">
      {{
        uiText(
          "只引用先前金额或明细列；来源缺失不补零，按字段小数位四舍五入。服务端重新计算，结果不可手填。",
        )
      }}
    </p>
  </div>
</template>
<script setup lang="ts">
import "./computationMessages";
import { computed } from "vue";
import { uiText } from "@/i18n/uiText";
import type {
  OnlineFormComputation,
  OnlineFormField,
  OnlineFormOperand,
} from "@/api";
const props = defineProps<{
  modelValue?: OnlineFormComputation;
  fields: OnlineFormField[];
}>();
const emit = defineEmits<{
  "update:modelValue": [value: OnlineFormComputation | undefined];
}>();
const operations = [
  { value: "manual", label: "手动输入" },
  { value: "add", label: "加法" },
  { value: "subtract", label: "减法" },
  { value: "multiply", label: "乘法" },
  { value: "divide", label: "除法" },
  { value: "sum", label: "明细金额合计" },
];
const sources = computed(() =>
  props.fields.filter((field) => field.type === "decimal"),
);
const details = computed(() =>
  props.fields.filter(
    (field) =>
      field.type === "detail" &&
      field.fields?.some((child) => child.type === "decimal"),
  ),
);
const detailColumns = computed(() =>
  props.modelValue?.op === "sum"
    ? details.value
        .find(
          (detail) =>
            detail.key === (props.modelValue as { detail: string }).detail,
        )
        ?.fields?.filter((field) => field.type === "decimal") || []
    : [],
);
function operand(index: number): OnlineFormOperand | undefined {
  return props.modelValue && props.modelValue.op !== "sum"
    ? props.modelValue.operands[index]
    : undefined;
}
function sourceValue(index: number) {
  const value = operand(index);
  return value && ("field" in value ? value.field : value.literal);
}
function changeOperation(operation: string) {
  if (operation === "manual") emit("update:modelValue", undefined);
  else if (operation === "sum") changeDetail(details.value[0]?.key || "");
  else if (["add", "subtract", "multiply", "divide"].includes(operation))
    emit("update:modelValue", {
      op: operation as "add" | "subtract" | "multiply" | "divide",
      operands: [{ literal: "0" }, { literal: "1" }],
    });
}
function changeDetail(key: string) {
  emit("update:modelValue", {
    op: "sum",
    detail: key,
    field:
      details.value
        .find((detail) => detail.key === key)
        ?.fields?.find((field) => field.type === "decimal")?.key || "",
  });
}
function setOperand(index: number, value: OnlineFormOperand) {
  if (!props.modelValue || props.modelValue.op === "sum") return;
  const operands: [OnlineFormOperand, OnlineFormOperand] = [
    ...props.modelValue.operands,
  ];
  operands[index] = value;
  emit("update:modelValue", { ...props.modelValue, operands });
}
</script>
<style scoped>
.computation {
  min-width: 0;
}
.operands {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.hint {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
@media (max-width: 768px) {
  .operands {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
