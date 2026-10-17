import type {
  OnlineFormCondition,
  OnlineFormDefinition,
  OnlineFormField,
} from "@/api";

export type FormValues = Record<string, unknown>;
export function isEmpty(value: unknown) {
  return (
    value == null ||
    (typeof value === "string" && !value.trim()) ||
    (Array.isArray(value) && !value.length)
  );
}
function numericDecimal(value: unknown): bigint | undefined {
  if (typeof value !== "string" || !/^-?\d{1,18}(?:\.\d{1,8})?$/.test(value))
    return;
  const [whole = "", fraction = ""] = value.replace("-", "").split(".");
  return (
    BigInt(whole + fraction.padEnd(8, "0")) * (value.startsWith("-") ? -1n : 1n)
  );
}
function comparable(raw: unknown, kind?: OnlineFormField["type"]) {
  if (kind === "decimal") return numericDecimal(raw);
  if (kind === "datetime")
    return typeof raw === "string" && Number.isFinite(Date.parse(raw))
      ? Date.parse(raw)
      : undefined;
  return typeof raw === "number" ||
    typeof raw === "string" ||
    typeof raw === "boolean"
    ? raw
    : undefined;
}
export function matches(
  conditions: OnlineFormCondition[] | undefined,
  values: FormValues,
  fields: OnlineFormField[] = [],
): boolean {
  return (
    !conditions ||
    conditions.every((rule) => {
      const kind = fields.find((f) => f.key === rule.field)?.type;
      const raw = comparable(values[rule.field], kind),
        expected = comparable(rule.value, kind);
      switch (rule.op) {
        case "eq":
          return raw === expected;
        case "ne":
          return raw !== expected;
        case "in":
          return (
            Array.isArray(rule.value) &&
            rule.value.some((v) => comparable(v, kind) === raw)
          );
        case "empty":
          return isEmpty(raw);
        case "not_empty":
          return !isEmpty(raw);
        case "lt":
          return raw != null && expected != null && raw < expected;
        case "lte":
          return raw != null && expected != null && raw <= expected;
        case "gt":
          return raw != null && expected != null && raw > expected;
        case "gte":
          return raw != null && expected != null && raw >= expected;
      }
    })
  );
}
export function initialValues(fields: OnlineFormField[]): FormValues {
  return Object.fromEntries(
    fields
      .filter((f) => f.default !== undefined || f.type === "boolean")
      .map((f) => [
        f.key,
        f.default === undefined ? false : JSON.parse(JSON.stringify(f.default)),
      ]),
  );
}
/** 按声明顺序求值。隐藏数据不参与后续条件，也不会被提交。 */
export function activeValues(
  fields: OnlineFormField[],
  values: FormValues,
): FormValues {
  const result: FormValues = {};
  for (const field of fields) {
    if (!matches(field.visible_when, result, fields)) continue;
    const raw = values[field.key] ?? field.default;
    if (!isEmpty(raw))
      result[field.key] =
        field.type === "detail" && Array.isArray(raw)
          ? raw.map((row) =>
              activeValues(field.fields || [], row as FormValues),
            )
          : raw;
  }
  return result;
}
export function visibleFields(fields: OnlineFormField[], values: FormValues) {
  const active: FormValues = {};
  return fields.filter((field) => {
    if (!matches(field.visible_when, active, fields)) return false;
    const raw = values[field.key] ?? field.default;
    if (!isEmpty(raw)) active[field.key] = raw;
    return true;
  });
}
export function required(
  field: OnlineFormField,
  values: FormValues,
  fields: OnlineFormField[] = [],
) {
  return (
    field.required ||
    (!!field.required_when && matches(field.required_when, values, fields))
  );
}
export function upgrade(
  definition: OnlineFormDefinition,
): OnlineFormDefinition {
  return {
    schema_version: 2,
    sections: [],
    rules: [],
    ...JSON.parse(JSON.stringify(definition)),
  };
}
export function fieldErrors(error: unknown): Record<string, string> {
  const data = (error as { response?: { data?: { data?: unknown } } })?.response
    ?.data?.data;
  const result: Record<string, string> = {};
  function visit(value: unknown, path: string) {
    if (Array.isArray(value) && value.every((item) => typeof item === "string"))
      result[path] = value.join("; ");
    else if (value && typeof value === "object")
      for (const [key, child] of Object.entries(value))
        visit(child, path ? `${path}.${key}` : key);
    else if (typeof value === "string") result[path] = value;
  }
  visit(data, "");
  return result;
}
