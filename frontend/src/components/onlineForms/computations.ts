import type { OnlineFormComputation } from "@/api";
import type { FormValues } from "./runtime";

const unit = 100000000n;
function decimal(value: unknown): bigint | undefined {
  if (typeof value !== "string" || !/^-?\d{1,18}(?:\.\d{1,8})?$/.test(value))
    return;
  const [whole = "", fraction = ""] = value.replace("-", "").split(".");
  const coefficient = BigInt(whole + fraction);
  if (coefficient.toString().length > 18) return;
  return (
    BigInt(whole + fraction.padEnd(8, "0")) * (value.startsWith("-") ? -1n : 1n)
  );
}

/** BigInt 有理数计算和 HALF_UP 定点舍入，与服务端 Decimal 协议相同。 */
export function calculateDecimal(
  computation: OnlineFormComputation,
  values: FormValues,
  scale: number,
): string | undefined {
  if (!Number.isInteger(scale) || scale < 0 || scale > 8) return;
  let numerator: bigint,
    denominator = unit;
  if (computation.op === "sum") {
    const rows = values[computation.detail];
    if (!Array.isArray(rows) || !rows.length) return;
    const amounts = rows.map((row) =>
      decimal((row as FormValues)[computation.field]),
    );
    if (amounts.some((value) => value === undefined)) return;
    numerator = (amounts as bigint[]).reduce((sum, amount) => sum + amount, 0n);
  } else {
    const operands = computation.operands.map((operand) =>
      decimal("field" in operand ? values[operand.field] : operand.literal),
    );
    const left = operands[0],
      right = operands[1];
    if (left === undefined || right === undefined) return;
    switch (computation.op) {
      case "add":
        numerator = left + right;
        break;
      case "subtract":
        numerator = left - right;
        break;
      case "multiply":
        numerator = left * right;
        denominator = unit * unit;
        break;
      case "divide":
        if (right === 0n) throw new Error("计算字段不能除以零");
        numerator = left;
        denominator = right;
        break;
    }
  }
  const negative = numerator < 0n !== denominator < 0n;
  numerator = (numerator < 0n ? -numerator : numerator) * 10n ** BigInt(scale);
  denominator = denominator < 0n ? -denominator : denominator;
  let rounded = numerator / denominator;
  if ((numerator % denominator) * 2n >= denominator) rounded++;
  if (rounded.toString().length > 18)
    throw new Error("计算结果超出金额精度限制");
  const digits = rounded.toString().padStart(scale + 1, "0");
  return `${negative && rounded !== 0n ? "-" : ""}${scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits}`;
}

export function computationError(
  computation: OnlineFormComputation | undefined,
  values: FormValues,
  scale = 2,
): string {
  if (!computation) return "";
  try {
    calculateDecimal(computation, values, scale);
    return "";
  } catch (error) {
    return error instanceof Error ? error.message : "";
  }
}
