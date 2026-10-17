<template>
  <div class="designer-fields">
    <el-button :disabled="disabled || modelValue.length >= 50" @click="add">{{
      uiText("添加字段")
    }}</el-button>
    <el-empty v-if="!modelValue.length" :description="uiText('请添加字段')" />
    <el-collapse>
      <el-collapse-item
        v-for="(field, index) in modelValue"
        :key="index"
        :name="index"
      >
        <template #title
          ><span class="field-title"
            >{{ index + 1 }}. {{ field.label }}
            <small>{{ field.key }} · {{ field.type }}</small></span
          ></template
        >
        <div class="toolbar">
          <el-button
            :disabled="disabled || index === 0"
            :aria-label="uiText('上移字段')"
            @click="move(index, -1)"
            >{{ uiText("上移") }}</el-button
          ><el-button
            :disabled="disabled || index === modelValue.length - 1"
            :aria-label="uiText('下移字段')"
            @click="move(index, 1)"
            >{{ uiText("下移") }}</el-button
          ><el-button type="danger" plain @click="remove(index)">{{
            uiText("删除字段")
          }}</el-button>
        </div>
        <div class="settings-grid">
          <el-form-item :label="uiText('标识')"
            ><el-input
              :model-value="field.key"
              :aria-label="uiText('字段标识')"
              :maxlength="40"
              @update:model-value="set(index, 'key', $event)"
          /></el-form-item>
          <el-form-item :label="uiText('标签')"
            ><el-input
              :model-value="field.label"
              :aria-label="uiText('字段标签')"
              :maxlength="120"
              @update:model-value="set(index, 'label', $event)"
          /></el-form-item>
          <el-form-item :label="uiText('类型')"
            ><el-select
              :model-value="field.type"
              :aria-label="uiText('字段类型')"
              @update:model-value="changeType(index, $event)"
              ><el-option
                v-for="type in types.filter(
                  (t) => !child || t.value !== 'detail',
                )"
                :key="type.value"
                :label="uiText(type.label)"
                :value="type.value" /></el-select
          ></el-form-item>
          <el-form-item :label="uiText('必填')"
            ><el-switch
              :model-value="field.required"
              :aria-label="uiText('字段必填')"
              @update:model-value="set(index, 'required', $event)"
          /></el-form-item>
          <el-form-item v-if="!child" :label="uiText('所属分组')"
            ><el-select
              :model-value="field.section || ''"
              :aria-label="uiText('所属分组')"
              @update:model-value="set(index, 'section', $event)"
              ><el-option :label="uiText('不分组')" value="" /><el-option
                v-for="section in sections"
                :key="section.key"
                :label="section.title"
                :value="section.key" /></el-select
          ></el-form-item>
          <el-form-item :label="uiText('占用列数')"
            ><el-select
              :model-value="field.span || 1"
              :aria-label="uiText('占用列数')"
              @update:model-value="set(index, 'span', $event)"
              ><el-option :label="uiText('半行')" :value="1" /><el-option
                :label="uiText('整行')"
                :value="2" /></el-select
          ></el-form-item>
          <el-form-item :label="uiText('帮助说明')"
            ><el-input
              :model-value="field.help || ''"
              :maxlength="500"
              @update:model-value="set(index, 'help', $event)"
          /></el-form-item>
          <el-form-item
            v-if="field.type !== 'detail'"
            :label="uiText('占位提示')"
            ><el-input
              :model-value="field.placeholder || ''"
              :maxlength="500"
              @update:model-value="set(index, 'placeholder', $event)"
          /></el-form-item>
          <el-form-item
            v-if="['select', 'multiselect'].includes(field.type)"
            :label="uiText('选项（每行一个）')"
            class="wide"
            ><el-input
              :model-value="(field.options || []).join('\n')"
              type="textarea"
              :rows="3"
              @update:model-value="set(index, 'options', $event.split('\n'))"
          /></el-form-item>
          <el-form-item
            v-if="['text', 'textarea'].includes(field.type)"
            :label="uiText('文本长度上限')"
            ><el-input-number
              :model-value="
                field.max_length || (field.type === 'text' ? 500 : 2000)
              "
              :min="1"
              :max="2000"
              :precision="0"
              @update:model-value="set(index, 'max_length', $event)"
          /></el-form-item>
          <el-form-item
            v-if="field.type === 'decimal'"
            :label="uiText('小数位数')"
            ><el-input-number
              :model-value="field.scale ?? 2"
              :min="0"
              :max="8"
              :precision="0"
              @update:model-value="set(index, 'scale', $event)"
          /></el-form-item>
          <template v-if="['number', 'decimal'].includes(field.type)">
            <el-form-item
              v-for="bound in ['min', 'max'] as const"
              :key="bound"
              :label="uiText(bound === 'min' ? '最小值' : '最大值')"
              ><el-input
                :model-value="String(field[bound] ?? '')"
                inputmode="decimal"
                @update:model-value="
                  set(
                    index,
                    bound,
                    $event === ''
                      ? undefined
                      : field.type === 'number'
                        ? Number($event)
                        : $event,
                  )
                "
            /></el-form-item>
          </template>
          <template v-if="field.type === 'detail'">
            <el-form-item :label="uiText('最少行数')"
              ><el-input-number
                :model-value="field.min_rows || 0"
                :min="0"
                :max="100"
                :precision="0"
                @update:model-value="set(index, 'min_rows', $event)"
            /></el-form-item>
            <el-form-item :label="uiText('最多行数')"
              ><el-input-number
                :model-value="field.max_rows || 50"
                :min="1"
                :max="100"
                :precision="0"
                @update:model-value="set(index, 'max_rows', $event)"
            /></el-form-item>
          </template>
          <div v-else class="wide default-row">
            <el-checkbox
              :model-value="field.default !== undefined"
              @update:model-value="toggleDefault(index, $event === true)"
              >{{ uiText("设置默认值") }}</el-checkbox
            ><OnlineFieldInput
              v-if="field.default !== undefined"
              :id="`${uid}-default-${index}`"
              :field="{
                ...field,
                label: uiText('默认值：{p0}', { p0: field.label }),
              }"
              :model-value="field.default"
              @update:model-value="set(index, 'default', $event)"
            />
          </div>
        </div>
        <el-form-item :label="uiText('显示条件')"
          ><ConditionEditor
            :id="`visible-${index}`"
            :model-value="field.visible_when || []"
            :fields="modelValue.slice(0, index)"
            @update:model-value="
              set(index, 'visible_when', $event.length ? $event : undefined)
            "
        /></el-form-item>
        <el-form-item :label="uiText('条件必填')"
          ><ConditionEditor
            :id="`required-${index}`"
            :model-value="field.required_when || []"
            :fields="modelValue.slice(0, index)"
            @update:model-value="
              set(index, 'required_when', $event.length ? $event : undefined)
            "
        /></el-form-item>
        <div v-if="field.type === 'detail'" class="child-fields">
          <h4>{{ uiText("明细字段") }}</h4>
          <FieldDesigner
            :model-value="field.fields || []"
            child
            @update:model-value="set(index, 'fields', $event)"
          />
          <h4>{{ uiText("明细行内校验") }}</h4>
          <ComparisonEditor
            :model-value="field.rules || []"
            :fields="field.fields || []"
            @update:model-value="set(index, 'rules', $event)"
          />
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>
<script setup lang="ts">
import "./messages";
import { useId } from "vue";
import type { OnlineFormField } from "@/api";
import { uiText } from "@/i18n/uiText";
import ConditionEditor from "./ConditionEditor.vue";
import { useFormDisabled } from "element-plus";
import ComparisonEditor from "./ComparisonEditor.vue";
import OnlineFieldInput from "./OnlineFieldInput.vue";
const props = withDefaults(
  defineProps<{
    modelValue: OnlineFormField[];
    child?: boolean;
    sections?: { key: string; title: string }[];
  }>(),
  { sections: () => [] },
);
const emit = defineEmits<{ "update:modelValue": [value: OnlineFormField[]] }>();
const disabled = useFormDisabled();
const uid = useId();
const types = [
  { value: "text", label: "单行文本" },
  { value: "textarea", label: "多行文本" },
  { value: "number", label: "数值" },
  { value: "decimal", label: "精确金额" },
  { value: "select", label: "单选" },
  { value: "multiselect", label: "多选" },
  { value: "date", label: "日期" },
  { value: "datetime", label: "日期时间" },
  { value: "boolean", label: "开关" },
  { value: "detail", label: "明细子表" },
];
function set(index: number, key: keyof OnlineFormField, value: unknown) {
  const rows = props.modelValue.map((field, i) =>
    i === index ? { ...field, [key]: value } : field,
  );
  if (value === undefined) delete rows[index]![key];
  emit("update:modelValue", rows);
}
function add() {
  emit("update:modelValue", [
    ...props.modelValue,
    {
      key: `field_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
      label: uiText("新字段"),
      type: "text",
      required: false,
      span: 1,
    },
  ]);
}
function move(index: number, offset: number) {
  const rows = [...props.modelValue];
  const [field] = rows.splice(index, 1);
  if (field) rows.splice(index + offset, 0, field);
  emit("update:modelValue", rows);
}
function remove(index: number) {
  emit(
    "update:modelValue",
    props.modelValue.filter((_f, i) => i !== index),
  );
}
function changeType(index: number, type: OnlineFormField["type"]) {
  const current = props.modelValue[index]!;
  const field: OnlineFormField = {
    key: current.key,
    label: current.label,
    required: current.required,
    type,
    span: type === "detail" ? 2 : current.span || 1,
    ...(!props.child ? { section: current.section || "" } : {}),
  };
  if (type === "select" || type === "multiselect") field.options = ["A", "B"];
  if (type === "detail")
    Object.assign(field, {
      fields: [
        { key: "title", label: uiText("名称"), type: "text", required: true },
      ],
      min_rows: 0,
      max_rows: 50,
      rules: [],
    });
  emit(
    "update:modelValue",
    props.modelValue.map((f, i) => (i === index ? field : f)),
  );
}
function toggleDefault(index: number, enabled: boolean) {
  const field = props.modelValue[index]!;
  set(
    index,
    "default",
    enabled
      ? field.type === "boolean"
        ? false
        : field.type === "number"
          ? 0
          : field.type === "decimal"
            ? "0.00"
            : field.type === "select"
              ? field.options?.[0] || ""
              : field.type === "multiselect"
                ? []
                : ""
      : undefined,
  );
}
</script>
<style scoped>
.designer-fields {
  min-width: 0;
}
.toolbar {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin: 8px 0 16px;
  flex-wrap: wrap;
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.wide {
  grid-column: 1/-1;
}
.field-title {
  overflow-wrap: anywhere;
  text-align: left;
  line-height: 1.6;
}
.field-title small {
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}
.child-fields {
  border-left: 3px solid var(--el-border-color);
  padding-left: 16px;
}
.default-row {
  display: grid;
  gap: 8px;
  margin-bottom: 18px;
}
.designer-fields :deep(.el-form-item__content) {
  min-width: 0;
}
.designer-fields :deep(.el-collapse-item__header) {
  min-height: 48px;
  height: auto;
  padding: 10px 0;
}
@media (max-width: 768px) {
  .settings-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .toolbar button {
    min-height: 44px;
  }
  .child-fields {
    padding-left: 10px;
  }
}
</style>
