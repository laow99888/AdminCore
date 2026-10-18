import { afterEach, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElSelect } from "element-plus";
import type { OnlineFormComputation, OnlineFormField } from "../src/api";
import {
  calculateDecimal,
  computationError,
} from "../src/components/onlineForms/computations";
import {
  activeValues,
  required,
  submissionValues,
  visibleFields,
} from "../src/components/onlineForms/runtime";
import Renderer from "../src/components/onlineForms/OnlineFormRenderer.vue";
import Editor from "../src/components/onlineForms/ComputationEditor.vue";
import FieldDesigner from "../src/components/onlineForms/FieldDesigner.vue";

const wrappers: VueWrapper[] = [];
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = "";
});
const amount = (
  key: string,
  extra: Partial<OnlineFormField> = {},
): OnlineFormField => ({
  key,
  label: key,
  type: "decimal",
  required: false,
  scale: 2,
  ...extra,
});
const binary = (
  op: "add" | "subtract" | "multiply" | "divide",
): OnlineFormComputation => ({
  op,
  operands: [{ field: "price" }, { field: "quantity" }],
});

it.each([
  ["add", "0.10", "0.20", "0.30"],
  ["subtract", "0.10", "0.20", "-0.10"],
  ["multiply", "0.10", "0.20", "0.02"],
  ["divide", "1.00", "6.00", "0.17"],
  ["divide", "-1.00", "8.00", "-0.13"],
  ["divide", "1.00", "-8.00", "-0.13"],
  ["multiply", "-0.01", "0.01", "0.00"],
  ["add", "9007199254740991.00", "0.01", "9007199254740991.01"],
] as const)(
  "十进制预览遵守服务端舍入契约：%s %s %s",
  (op, price, quantity, result) => {
    expect(calculateDecimal(binary(op), { price, quantity }, 2)).toBe(result);
  },
);

it("缺值和非法输入不补零，除零及精度溢出有字段错误", () => {
  expect(calculateDecimal(binary("add"), { price: "1.00" }, 2)).toBeUndefined();
  expect(
    calculateDecimal(binary("add"), { price: 1, quantity: "1.00" }, 2),
  ).toBeUndefined();
  expect(
    computationError(binary("divide"), { price: "1.00", quantity: "0" }),
  ).toBe("计算字段不能除以零");
  expect(
    computationError(binary("multiply"), {
      price: "9999999999999999.99",
      quantity: "2",
    }),
  ).toBe("计算结果超出金额精度限制");
  expect(
    calculateDecimal(
      { op: "divide", operands: [{ literal: "1" }, { literal: "3" }] },
      {},
      8,
    ),
  ).toBe("0.33333333");
});

it("链式计算参与条件，提交剔除客户端计算值及隐藏来源", () => {
  const fields = [
    amount("price"),
    amount("quantity"),
    amount("total", { computation: binary("multiply") }),
    amount("discount", {
      computation: {
        op: "multiply",
        operands: [{ field: "total" }, { literal: "0.9" }],
      },
    }),
    {
      key: "reason",
      label: "原因",
      type: "text",
      required: false,
      visible_when: [{ field: "total", op: "gte", value: "100.00" }],
      required_when: [{ field: "discount", op: "gte", value: "90.00" }],
    } satisfies OnlineFormField,
  ];
  const values = {
    price: "50.00",
    quantity: "2",
    total: "999",
    discount: "999",
    reason: "说明",
  };
  expect(activeValues(fields, values)).toEqual({
    price: "50.00",
    quantity: "2",
    total: "100.00",
    discount: "90.00",
    reason: "说明",
  });
  expect(required(fields[4]!, activeValues(fields, values), fields)).toBe(true);
  expect(submissionValues(fields, values)).toEqual({
    price: "50.00",
    quantity: "2",
    reason: "说明",
  });
  fields[0]!.visible_when = [{ field: "gate", op: "eq", value: true }];
  expect(activeValues(fields, values)).toEqual({ quantity: "2" });
  expect(
    visibleFields(fields, values).some((field) => field.key === "reason"),
  ).toBe(false);
});

it("明细先逐行计算再汇总，空明细或不完整行不产生低估总额", () => {
  const fields = [
    {
      key: "lines",
      label: "明细",
      type: "detail",
      required: false,
      fields: [
        amount("price"),
        amount("quantity"),
        amount("subtotal", { computation: binary("multiply") }),
      ],
    } satisfies OnlineFormField,
    amount("grand", {
      computation: { op: "sum", detail: "lines", field: "subtotal" },
    }),
  ];
  const values = {
    lines: [
      { price: "0.10", quantity: "3", subtotal: "999" },
      { price: "1.25", quantity: "2" },
    ],
    grand: "999",
  };
  expect(activeValues(fields, values).grand).toBe("2.80");
  expect(submissionValues(fields, values)).toEqual({
    lines: [
      { price: "0.10", quantity: "3" },
      { price: "1.25", quantity: "2" },
    ],
  });
  expect(
    activeValues(fields, {
      lines: [{ price: "1" }, { price: "2", quantity: "3" }],
    }).grand,
  ).toBeUndefined();
  expect(activeValues(fields, { lines: [] }).grand).toBeUndefined();
});

it("真实渲染器计算只读并随来源更新，除零错误可见，整表只读继承生效", async () => {
  const fields = [
    amount("price"),
    amount("quantity"),
    amount("total", { computation: binary("divide") }),
  ];
  const wrapper = mount(
    defineComponent({
      components: { Renderer },
      data: () => ({
        fields,
        values: { price: "1.00", quantity: "8", total: "999" },
        disabled: false,
      }),
      template:
        '<Renderer v-model="values" :definition="{schema_version: 2, fields}" :disabled="disabled" />',
    }),
    { global: { plugins: [ElementPlus] } },
  );
  wrappers.push(wrapper);
  expect(
    (wrapper.get('[aria-label="total"]').element as HTMLInputElement).value,
  ).toBe("0.13");
  expect(
    wrapper.get('[aria-label="total"]').attributes("disabled"),
  ).toBeDefined();
  expect(
    wrapper.get('[aria-label="price"]').attributes("disabled"),
  ).toBeUndefined();
  await wrapper.get('[aria-label="quantity"]').setValue("0");
  await flushPromises();
  await vi.waitFor(() => expect(wrapper.text()).toContain("计算字段不能除以零"));
  expect(
    (wrapper.get('[aria-label="total"]').element as HTMLInputElement).value,
  ).toBe("");
  await wrapper.setData({ disabled: true });
  expect(
    wrapper.get('[aria-label="price"]').attributes("disabled"),
  ).toBeDefined();
});

it("计算配置只提供金额来源、明确常量和明细金额列，并支持返回手动输入", async () => {
  const fields = [
    amount("price"),
    {
      key: "title",
      label: "标题",
      type: "text",
      required: false,
    } satisfies OnlineFormField,
    {
      key: "lines",
      label: "明细",
      type: "detail",
      required: false,
      fields: [amount("subtotal")],
    } satisfies OnlineFormField,
  ];
  const wrapper = mount(Editor, {
    props: { fields },
    global: { plugins: [ElementPlus] },
  });
  wrappers.push(wrapper);
  wrapper
    .findAllComponents(ElSelect)[0]!
    .vm.$emit("update:modelValue", "multiply");
  await flushPromises();
  const computation = wrapper.emitted(
    "update:modelValue",
  )![0]![0] as OnlineFormComputation;
  await wrapper.setProps({ modelValue: computation });
  wrapper
    .findAllComponents(ElSelect)[1]!
    .vm.$emit("update:modelValue", "field");
  await flushPromises();
  expect(wrapper.emitted("update:modelValue")!.at(-1)![0]).toEqual({
    op: "multiply",
    operands: [{ field: "price" }, { literal: "1" }],
  });
  wrapper.findAllComponents(ElSelect)[0]!.vm.$emit("update:modelValue", "sum");
  await flushPromises();
  expect(wrapper.emitted("update:modelValue")!.at(-1)![0]).toEqual({
    op: "sum",
    detail: "lines",
    field: "subtotal",
  });
  wrapper
    .findAllComponents(ElSelect)[0]!
    .vm.$emit("update:modelValue", "manual");
  await flushPromises();
  expect(wrapper.emitted("update:modelValue")!.at(-1)![0]).toBeUndefined();
});

it("设计器设置计算时移除默认值，引用范围限制在当前字段之前", async () => {
  const wrapper = mount(FieldDesigner, {
    props: {
      modelValue: [
        amount("price"),
        amount("total", { default: "1.00" }),
        amount("later"),
      ],
    },
    global: { plugins: [ElementPlus] },
  });
  wrappers.push(wrapper);
  const editor = wrapper.findAllComponents(Editor)[1]!;
  expect(
    editor.props("fields").map((field: OnlineFormField) => field.key),
  ).toEqual(["price"]);
  editor.vm.$emit("update:modelValue", binary("multiply"));
  await flushPromises();
  const fields = wrapper
    .emitted("update:modelValue")!
    .at(-1)![0] as OnlineFormField[];
  expect(fields[1]!.computation).toEqual(binary("multiply"));
  expect(fields[1]).not.toHaveProperty("default");
});
