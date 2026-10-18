import { registerUiMessages } from "@/i18n/uiText";
registerUiMessages({
  金额来源: "Amount source",
  手动输入: "Manual entry",
  加法: "Addition",
  减法: "Subtraction",
  乘法: "Multiplication",
  除法: "Division",
  明细金额合计: "Detail amount total",
  汇总明细: "Source detail",
  汇总金额列: "Amount column",
  金额字段: "Amount field",
  十进制常量: "Decimal constant",
  "第 {p0} 个计算来源": "Operand {p0} source",
  "第 {p0} 个金额字段": "Operand {p0} amount field",
  "第 {p0} 个十进制常量": "Operand {p0} decimal constant",
  "只引用先前金额或明细列；来源缺失不补零，按字段小数位四舍五入。服务端重新计算，结果不可手填。":
    "Only earlier amount fields or detail columns can be referenced. Missing sources remain empty. Results use half-up rounding, are read-only and are recalculated by the server.",
  计算字段不能除以零: "Calculated fields cannot divide by zero",
  计算结果超出金额精度限制: "Calculated amount exceeds the precision limit",
});
