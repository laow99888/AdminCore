<template>
  <div class="field-grid">
    <template v-for="field in visible" :key="field.key">
      <div
        :class="[
          'field',
          { wide: field.span === 2 || field.type === 'detail' },
        ]"
      >
        <el-form-item
          :label="field.label"
          :for="`${prefix}${field.key}`"
          :required="required(field, active, fields)"
          :error="errors[`${prefix}${field.key}`]"
        >
          <template v-if="field.type === 'detail'">
            <div class="details">
              <p class="help">
                {{
                  uiText("明细行数：{p0} 至 {p1}", {
                    p0: Math.max(
                      field.min_rows || 0,
                      required(field, active, fields) ? 1 : 0,
                    ),
                    p1: field.max_rows || 50,
                  })
                }}
              </p>
              <section
                v-for="(row, index) in rows(field)"
                :key="index"
                class="detail-row"
              >
                <div class="row-head">
                  <strong>{{ uiText("第 {p0} 行", { p0: index + 1 }) }}</strong
                  ><el-button
                    :aria-label="uiText('删除第 {p0} 行', { p0: index + 1 })"
                    type="danger"
                    plain
                    :disabled="disabled"
                    @click="removeRow(field, index)"
                    >{{ uiText("删除") }}</el-button
                  >
                </div>
                <OnlineFormFields
                  :fields="field.fields || []"
                  :model-value="row"
                  :prefix="`${prefix}${field.key}.${index}.`"
                  :errors="errors"
                  :disabled="disabled"
                  @update:model-value="updateRow(field, index, $event)"
                />
              </section>
              <el-button
                :disabled="
                  disabled || rows(field).length >= (field.max_rows || 50)
                "
                @click="addRow(field)"
                >{{ uiText("添加明细") }}</el-button
              >
            </div>
          </template>
          <OnlineFieldInput
            v-else
            :id="`${prefix}${field.key}`"
            :field="field"
            :model-value="modelValue[field.key]"
            @update:model-value="update(field.key, $event)"
          />
          <small v-if="field.help" class="help">{{ field.help }}</small>
        </el-form-item>
      </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import "./messages";
import { computed } from "vue";
import type { OnlineFormField } from "@/api";
import { uiText } from "@/i18n/uiText";
import OnlineFieldInput from "./OnlineFieldInput.vue";
import {
  activeValues,
  initialValues,
  required,
  visibleFields,
  type FormValues,
} from "./runtime";
const props = withDefaults(
  defineProps<{
    fields: OnlineFormField[];
    modelValue: FormValues;
    prefix?: string;
    errors?: Record<string, string>;
    disabled?: boolean;
    section?: string;
  }>(),
  { prefix: "", errors: () => ({}) },
);
const emit = defineEmits<{ "update:modelValue": [value: FormValues] }>();
const active = computed(() => activeValues(props.fields, props.modelValue));
const visible = computed(() =>
  visibleFields(props.fields, props.modelValue).filter(
    (field) =>
      props.section === undefined || (field.section || "") === props.section,
  ),
);
function update(key: string, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
function rows(field: OnlineFormField): FormValues[] {
  return Array.isArray(props.modelValue[field.key])
    ? (props.modelValue[field.key] as FormValues[])
    : [];
}
function addRow(field: OnlineFormField) {
  update(field.key, [...rows(field), initialValues(field.fields || [])]);
}
function removeRow(field: OnlineFormField, index: number) {
  update(
    field.key,
    rows(field).filter((_r, i) => i !== index),
  );
}
function updateRow(field: OnlineFormField, index: number, row: FormValues) {
  update(
    field.key,
    rows(field).map((r, i) => (i === index ? row : r)),
  );
}
</script>
<style scoped>
.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}
.field {
  min-width: 0;
}
.wide {
  grid-column: 1/-1;
}
.details {
  width: 100%;
  min-width: 0;
}
.detail-row {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 14px;
  margin: 12px 0;
}
.row-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.help {
  display: block;
  width: 100%;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 5px 0;
}
.field :deep(.el-form-item__content) {
  min-width: 0;
}
.field :deep(.el-input-number),
.field :deep(.el-date-editor) {
  width: 100%;
  max-width: 100%;
}
@media (max-width: 768px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .detail-row {
    padding: 10px;
  }
  .row-head button {
    min-height: 44px;
  }
}
</style>
