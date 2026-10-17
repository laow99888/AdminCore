<template>
  <div class="field-editor">
    <div class="head">
      <span>{{ uiText("字段配置") }} · {{ fields.length }}/50</span
      ><el-button :disabled="disabled || fields.length >= 50" @click="add">{{
        uiText("添加字段")
      }}</el-button>
    </div>
    <el-empty v-if="!fields.length" :description="uiText('请添加字段')" />
    <el-collapse v-model="active" accordion
      ><el-collapse-item
        v-for="(field, index) in fields"
        :key="index"
        :name="String(index)"
      >
        <template #title
          ><span
            >{{ field.label || uiText("新字段") }} · {{ field.name }}</span
          ></template
        >
        <el-form :disabled="disabled" label-position="top"
          ><div class="grid">
            <el-form-item :label="uiText('字段标识')" required
              ><el-input
                v-model="field.name"
                maxlength="30"
                :aria-label="uiText('字段标识')"
            /></el-form-item>
            <el-form-item :label="uiText('字段标签')" required
              ><el-input
                v-model="field.label"
                maxlength="40"
                :aria-label="uiText('字段标签')"
            /></el-form-item>
            <el-form-item :label="uiText('字段类型')"
              ><el-select
                :model-value="field.kind"
                :aria-label="uiText('字段类型')"
                @update:model-value="changeKind(index, $event)"
                ><el-option
                  v-for="kind in fieldKinds"
                  :key="kind.value"
                  :value="kind.value"
                  :label="uiText(kind.label)" /></el-select
            ></el-form-item>
            <el-form-item v-if="!detail" :label="uiText('查询方式')"
              ><el-select v-model="field.query" :aria-label="uiText('查询方式')"
                ><el-option value="none" :label="uiText('不查询')" /><el-option
                  value="eq"
                  :label="uiText('精确匹配')" /><el-option
                  v-if="['string', 'text'].includes(field.kind)"
                  value="contains"
                  :label="uiText('包含')" /><el-option
                  v-if="
                    ['integer', 'decimal', 'date', 'datetime'].includes(
                      field.kind,
                    )
                  "
                  value="range"
                  :label="uiText('范围')" /></el-select
            ></el-form-item>
            <el-form-item
              v-if="['string', 'text'].includes(field.kind)"
              :label="uiText('最大长度')"
              ><el-input-number
                v-model="field.max_length"
                :min="1"
                :max="10000"
                :precision="0"
                :aria-label="uiText('最大长度')"
            /></el-form-item>
            <template v-if="field.kind === 'integer'"
              ><el-form-item :label="uiText('最小值')"
                ><el-input-number
                  v-model="field.minimum as number"
                  :min="-2147483648"
                  :max="2147483647"
                  :precision="0"
                  :aria-label="uiText('最小值')" /></el-form-item
              ><el-form-item :label="uiText('最大值')"
                ><el-input-number
                  v-model="field.maximum as number"
                  :min="-2147483648"
                  :max="2147483647"
                  :precision="0"
                  :aria-label="uiText('最大值')" /></el-form-item
            ></template>
            <template v-if="field.kind === 'decimal'"
              ><el-form-item :label="uiText('总位数')"
                ><el-input-number
                  v-model="field.max_digits"
                  :min="2"
                  :max="18"
                  :precision="0"
                  :aria-label="uiText('总位数')" /></el-form-item
              ><el-form-item :label="uiText('小数位数')"
                ><el-input-number
                  v-model="field.decimal_places"
                  :min="0"
                  :max="8"
                  :precision="0"
                  :aria-label="uiText('小数位数')" /></el-form-item
              ><el-form-item :label="uiText('最小值')"
                ><el-input
                  :model-value="String(field.minimum ?? '')"
                  inputmode="decimal"
                  :aria-label="uiText('最小值')"
                  @update:model-value="
                    optional(field, 'minimum', $event)
                  " /></el-form-item
              ><el-form-item :label="uiText('最大值')"
                ><el-input
                  :model-value="String(field.maximum ?? '')"
                  inputmode="decimal"
                  :aria-label="uiText('最大值')"
                  @update:model-value="
                    optional(field, 'maximum', $event)
                  " /></el-form-item
            ></template>
            <el-form-item
              v-if="field.kind === 'dictionary'"
              :label="uiText('字典编码')"
              ><el-input
                v-model="field.dictionary"
                maxlength="64"
                :aria-label="uiText('字典编码')"
            /></el-form-item>
            <template v-if="field.kind === 'relation' && field.target"
              ><el-form-item :label="uiText('关联模块')"
                ><el-input
                  v-model="field.target.module"
                  maxlength="20"
                  :aria-label="uiText('关联模块')" /></el-form-item
              ><el-form-item :label="uiText('关联模型')"
                ><el-input
                  v-model="field.target.model"
                  maxlength="48"
                  :aria-label="uiText('关联模型')" /></el-form-item
              ><el-form-item :label="uiText('显示字段')"
                ><el-input
                  v-model="field.target.label"
                  maxlength="30"
                  :aria-label="uiText('显示字段')" /></el-form-item
            ></template>
            <el-form-item
              v-if="['string', 'boolean', 'enum'].includes(field.kind)"
              :label="uiText('控件')"
              ><el-select v-model="field.component" :aria-label="uiText('控件')"
                ><el-option
                  v-for="item in controls(field.kind)"
                  :key="item.value"
                  :value="item.value"
                  :label="uiText(item.label)" /></el-select
            ></el-form-item>
            <el-form-item
              v-if="
                ['string', 'text', 'decimal', 'dictionary'].includes(field.kind)
              "
              :label="uiText('默认值')"
              ><el-input
                :model-value="String(field.default ?? '')"
                :aria-label="uiText('默认值')"
                @update:model-value="field.default = $event"
            /></el-form-item>
            <el-form-item
              v-if="field.kind === 'integer'"
              :label="uiText('默认值')"
            >
              <el-input-number
                v-model="field.default as number"
                :min="Number(field.minimum ?? 0)"
                :max="Number(field.maximum ?? 1000000)"
                :precision="0"
                :aria-label="uiText('默认值')"
              />
            </el-form-item>
            <el-form-item
              v-if="field.kind === 'boolean'"
              :label="uiText('默认值')"
            >
              <el-switch
                :model-value="field.default === true"
                :aria-label="uiText('默认值')"
                @update:model-value="field.default = Boolean($event)"
              />
            </el-form-item>
            <el-form-item
              v-if="field.kind === 'enum'"
              :label="uiText('默认值')"
            >
              <el-select
                v-model="field.default as string"
                :aria-label="uiText('默认值')"
                clearable
                @clear="delete field.default"
              >
                <el-option
                  v-for="choice in field.choices"
                  :key="choice.value"
                  :value="choice.value"
                  :label="choice.label"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="field.kind === 'date' || field.kind === 'datetime'"
              :label="uiText('默认值')"
            >
              <el-date-picker
                v-model="field.default as string | null"
                :type="field.kind === 'date' ? 'date' : 'datetime'"
                :value-format="
                  field.kind === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm:ssZ'
                "
                :aria-label="uiText('默认值')"
              />
            </el-form-item>
          </div>
          <div class="flags">
            <el-checkbox v-model="field.required">{{
              uiText("必填")
            }}</el-checkbox
            ><el-checkbox v-model="field.list">{{
              uiText("列表显示")
            }}</el-checkbox
            ><el-checkbox v-model="field.form">{{
              uiText("表单可编辑")
            }}</el-checkbox
            ><el-checkbox v-if="!detail" v-model="field.sortable">{{
              uiText("允许排序")
            }}</el-checkbox
            ><el-checkbox v-model="field.indexed">{{
              uiText("建立索引")
            }}</el-checkbox
            ><el-checkbox
              v-if="!['text', 'relation', 'file'].includes(field.kind)"
              v-model="field.unique"
              >{{ uiText("唯一约束") }}</el-checkbox
            >
          </div>
          <template v-if="field.kind === 'enum'"
            ><p>{{ uiText("枚举选项") }}</p>
            <div
              v-for="(choice, choiceIndex) in field.choices"
              :key="choiceIndex"
              class="choice"
            >
              <el-input
                v-model="choice.value"
                :aria-label="uiText('枚举值') + ' ' + (choiceIndex + 1)"
                maxlength="80"
              /><el-input
                v-model="choice.label"
                :aria-label="uiText('枚举标签') + ' ' + (choiceIndex + 1)"
                maxlength="80"
              /><el-button
                :aria-label="uiText('删除选项') + ' ' + (choiceIndex + 1)"
                @click="field.choices?.splice(choiceIndex, 1)"
                >{{ uiText("删除") }}</el-button
              >
            </div>
            <el-button
              :disabled="(field.choices?.length ?? 0) >= 100"
              @click="field.choices?.push({ value: '', label: '' })"
              >{{ uiText("添加选项") }}</el-button
            ></template
          >
          <div class="actions">
            <el-button :disabled="index === 0" @click="move(index, -1)">{{
              uiText("上移")
            }}</el-button
            ><el-button
              :disabled="index === fields.length - 1"
              @click="move(index, 1)"
              >{{ uiText("下移") }}</el-button
            ><el-button type="danger" plain @click="fields.splice(index, 1)">{{
              uiText("删除字段")
            }}</el-button>
          </div>
        </el-form>
      </el-collapse-item></el-collapse
    >
  </div>
</template>
<script setup lang="ts">
import "./messages";
import { ref } from "vue";
import { uiText } from "@/i18n/uiText";
import {
  fieldKinds,
  newField,
  type GeneratedField,
  type FieldKind,
} from "./types";
const fields = defineModel<GeneratedField[]>({ required: true });
defineProps<{ disabled?: boolean; detail?: boolean }>();
const active = ref("0");
function add() {
  let index = fields.value.length + 1;
  while (fields.value.some((field) => field.name === `field_${index}`)) index++;
  fields.value.push(newField(index));
  active.value = String(fields.value.length - 1);
}
function move(index: number, delta: number) {
  const row = fields.value.splice(index, 1)[0]!;
  fields.value.splice(index + delta, 0, row);
  active.value = String(index + delta);
}
function optional(
  field: GeneratedField,
  key: "minimum" | "maximum",
  value: string,
) {
  if (value) field[key] = value;
  else delete field[key];
}
function controls(kind: FieldKind) {
  return kind === "boolean"
    ? [
        { value: "switch", label: "开关" },
        { value: "select", label: "下拉" },
      ]
    : kind === "enum"
      ? [
          { value: "select", label: "下拉" },
          { value: "radio", label: "单选" },
        ]
      : [
          { value: "input", label: "单行" },
          { value: "textarea", label: "多行" },
        ];
}
function changeKind(index: number, kind: FieldKind) {
  const old = fields.value[index]!;
  const field: GeneratedField = {
    name: old.name,
    label: old.label,
    kind,
    required: old.required,
    list: old.list,
    form: old.form,
    sortable: false,
    unique: false,
    indexed: false,
    query: "none",
  };
  if (kind === "string" || kind === "text")
    field.max_length = kind === "text" ? 2000 : 120;
  if (kind === "integer") {
    field.minimum = 0;
    field.maximum = 1000000;
  }
  if (kind === "decimal") {
    field.max_digits = 18;
    field.decimal_places = 2;
    field.minimum = "0";
  }
  if (kind === "enum") field.choices = [{ value: "draft", label: "草稿" }];
  if (kind === "relation")
    field.target = { module: "", model: "", label: "name" };
  if (kind === "dictionary") field.dictionary = "";
  fields.value[index] = field;
}
</script>
<style scoped>
.head,
.actions,
.choice,
.flags {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.head {
  justify-content: space-between;
  margin: 12px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.actions {
  margin-top: 16px;
}
.choice {
  margin-bottom: 8px;
}
.choice :deep(.el-input) {
  flex: 1;
  min-width: 90px;
}
.flags {
  margin: 8px 0;
}
:deep(.el-select) {
  width: 100%;
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
