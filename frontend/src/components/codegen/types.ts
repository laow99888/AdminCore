export type FieldKind =
  | "string"
  | "text"
  | "integer"
  | "boolean"
  | "decimal"
  | "date"
  | "datetime"
  | "enum"
  | "dictionary"
  | "relation"
  | "file";
export interface Choice {
  value: string;
  label: string;
}
export interface GeneratedField {
  name: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  default?: string | number | boolean | null;
  list?: boolean;
  form?: boolean;
  query?: "none" | "eq" | "contains" | "range";
  sortable?: boolean;
  unique?: boolean;
  indexed?: boolean;
  component?: string;
  max_length?: number;
  minimum?: number | string;
  maximum?: number | string;
  max_digits?: number;
  decimal_places?: number;
  choices?: Choice[];
  dictionary?: string;
  target?: { module: string; model: string; label: string };
}
export interface GeneratedDetail {
  name: string;
  label: string;
  model: string;
  fields: GeneratedField[];
  min_rows?: number;
  max_rows?: number;
}
export interface GeneratedSchema {
  schema_version: 2;
  module: string;
  title: string;
  model: string;
  structure: "single" | "tree" | "master_detail";
  fields: GeneratedField[];
  details: GeneratedDetail[];
  ordering?: string[];
  approval?: { flow_code: string; title_field: string };
  reports?: { dimensions: string[]; metrics: string[]; filters: string[] };
}
export type FieldValue = string | number | boolean | null;

export const fieldKinds: { value: FieldKind; label: string }[] = [
  { value: "string", label: "单行文本" },
  { value: "text", label: "多行文本" },
  { value: "integer", label: "整数" },
  { value: "boolean", label: "布尔值" },
  { value: "decimal", label: "金额/定点数" },
  { value: "date", label: "日期" },
  { value: "datetime", label: "日期时间" },
  { value: "enum", label: "固定枚举" },
  { value: "dictionary", label: "数据字典" },
  { value: "relation", label: "业务关联" },
  { value: "file", label: "附件引用" },
];
export function newField(index = 1): GeneratedField {
  return {
    name: `field_${index}`,
    label: "新字段",
    kind: "string",
    required: true,
    list: true,
    form: true,
    query: "none",
    max_length: 120,
  };
}
export function defaultValues(fields: GeneratedField[]) {
  return Object.fromEntries(
    fields
      .filter((field) => field.form !== false)
      .map((field) => [
        field.name,
        field.default ??
          (field.kind === "boolean"
            ? false
            : field.kind === "integer"
              ? (field.minimum ?? 0)
              : field.kind === "decimal"
                ? String(field.minimum ?? "0")
                : field.kind === "enum"
                  ? (field.choices?.[0]?.value ?? "")
                  : ["date", "datetime", "relation", "file"].includes(
                        field.kind,
                      )
                    ? null
                    : ""),
      ]),
  );
}
