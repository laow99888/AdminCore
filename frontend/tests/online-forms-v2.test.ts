import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { defineComponent, nextTick } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { createPinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import { useAuthStore } from "../src/stores/auth";
import {
  onlineFormsApi,
  type OnlineFormDefinition,
  type OnlineFormField,
} from "../src/api";
import {
  activeValues,
  initialValues,
  matches,
  visibleFields,
  required,
  fieldErrors,
} from "../src/components/onlineForms/runtime";
import Renderer from "../src/components/onlineForms/OnlineFormRenderer.vue";
import Runtime from "../src/views/onlineForms/OnlineFormRuntimeView.vue";
import Designer from "../src/views/onlineForms/OnlineFormDesignerView.vue";

vi.mock("../src/components/layout/AppLayout.vue", () => ({
  default: defineComponent({ template: "<main><slot /></main>" }),
}));
vi.mock("../src/api", () => ({
  onlineFormsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    publish: vi.fn(),
    published: vi.fn(),
    createRecord: vi.fn(),
    validate: vi.fn(),
  },
}));
beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(() => {
  localStorage.clear();
});
const fields: OnlineFormField[] = [
  {
    key: "show",
    label: "显示费用",
    type: "boolean",
    required: false,
    default: false,
  },
  {
    key: "amount",
    label: "费用",
    type: "decimal",
    required: true,
    scale: 2,
    visible_when: [{ field: "show", op: "eq", value: true }],
  },
  {
    key: "note",
    label: "说明",
    type: "text",
    required: false,
    visible_when: [{ field: "amount", op: "not_empty" }],
    required_when: [{ field: "amount", op: "gte", value: "100.00" }],
  },
  {
    key: "lines",
    label: "明细",
    type: "detail",
    required: false,
    min_rows: 1,
    max_rows: 2,
    fields: [
      { key: "name", label: "项目名称", type: "text", required: true },
      {
        key: "price",
        label: "单价",
        type: "decimal",
        required: true,
        scale: 2,
      },
    ],
  },
];
const definition: OnlineFormDefinition = { schema_version: 2, fields };

it("隐藏值及其后续依赖被剔除，金额大数比较不经过浮点数", () => {
  const values = {
    show: false,
    amount: "999.99",
    note: "旧值",
    lines: [{ name: "A", price: "0.10" }],
  };
  expect(activeValues(fields, values)).toEqual({
    show: false,
    lines: [{ name: "A", price: "0.10" }],
  });
  expect(visibleFields(fields, values).map((f) => f.key)).toEqual([
    "show",
    "lines",
  ]);
  expect(
    matches(
      [{ field: "amount", op: "eq", value: "1.00" }],
      { amount: "1.0" },
      fields,
    ),
  ).toBe(true);
  expect(
    matches(
      [{ field: "amount", op: "gt", value: "9999999999999999.98" }],
      { amount: "9999999999999999.99" },
      fields,
    ),
  ).toBe(true);
  expect(required(fields[2]!, { amount: "100.00" }, fields)).toBe(true);
  expect(required(fields[2]!, { amount: "99.99" }, fields)).toBe(false);
});

it("条件保留布尔与数字类型差异，支持集合、空值及带时区日期比较", () => {
  expect(
    matches([{ field: "show", op: "eq", value: true }], { show: 1 }, fields),
  ).toBe(false);
  expect(
    matches([{ field: "show", op: "in", value: [true] }], { show: 1 }, fields),
  ).toBe(false);
  expect(matches([{ field: "x", op: "empty" }], { x: "" })).toBe(true);
  expect(matches([{ field: "x", op: "not_empty" }], { x: false })).toBe(true);
  const times: OnlineFormField[] = [
    { key: "at", label: "时间", type: "datetime", required: false },
  ];
  expect(
    matches(
      [{ field: "at", op: "eq", value: "2026-10-18T04:00:00Z" }],
      { at: "2026-10-18T12:00:00+08:00" },
      times,
    ),
  ).toBe(true);
});

it("默认多选值使用独立副本，服务端嵌套错误保留到行字段", () => {
  const items: OnlineFormField[] = [
    {
      key: "choices",
      label: "选项",
      type: "multiselect",
      required: false,
      options: ["A"],
      default: ["A"],
    },
  ];
  const a = initialValues(items),
    b = initialValues(items);
  (a.choices as string[]).push("B");
  expect(b.choices).toEqual(["A"]);
  expect(
    fieldErrors({
      response: { data: { data: { lines: { "0": { price: ["精度错误"] } } } } },
    }),
  ).toEqual({ "lines.0.price": "精度错误" });
});

it("共用渲染器实时显隐、分组、添加删除明细并定位服务端行错误", async () => {
  const wrapper = mount(
    defineComponent({
      components: { Renderer },
      data: () => ({
        definition: {
          ...definition,
          sections: [{ key: "cost", title: "费用信息" }],
          fields: fields.map((f) => ({
            ...f,
            section: f.key === "lines" ? "cost" : "",
          })),
        },
        values: initialValues(fields),
        errors: { "lines.0.price": "金额精度错误" },
      }),
      template:
        '<Renderer v-model="values" :definition="definition" :errors="errors" />',
    }),
    { global: { plugins: [ElementPlus] } },
  );
  expect(wrapper.find('[aria-label="费用"]').exists()).toBe(false);
  await wrapper.get('[role="switch"]').trigger("click");
  await nextTick();
  expect(wrapper.find('[aria-label="费用"]').exists()).toBe(true);
  const add = () =>
    wrapper.findAll("button").find((b) => b.text() === "添加明细")!;
  await add().trigger("click");
  await nextTick();
  await vi.waitFor(() => expect(wrapper.text()).toContain("金额精度错误"));
  expect(wrapper.text()).toContain("费用信息");
  await add().trigger("click");
  await nextTick();
  expect(add().attributes("disabled")).toBeDefined();
  await wrapper.get('[aria-label="删除第 1 行"]').trigger("click");
  await nextTick();
  expect(add().attributes("disabled")).toBeUndefined();
});

async function harness(
  component: typeof Runtime | typeof Designer,
  path = "/online-forms/travel",
) {
  const pinia = createPinia(),
    auth = useAuthStore(pinia);
  auth.token = "isolated";
  auth.user = {
    id: "editor",
    username: "editor",
    email: "",
    avatar: "",
    permissions: ["*"],
    is_staff: true,
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/online-forms/:code?", component: { template: "<div />" } },
      { path: "/other", component: { template: "<div />" } },
    ],
  });
  await router.push(path);
  const wrapper = mount(component, {
    global: { plugins: [pinia, router, ElementPlus] },
  });
  await flushPromises();
  return { wrapper, router, auth };
}

it("实际填写失败保留输入及错误，相同内容重试沿用幂等键，成功后恢复默认值", async () => {
  vi.mocked(onlineFormsApi.published).mockResolvedValue({
    data: {
      data: {
        id: "f",
        name: "申请",
        code: "travel",
        status: "published",
        version: 1,
        definition: {
          schema_version: 2,
          fields: [
            {
              key: "title",
              label: "标题",
              type: "text",
              required: true,
              default: "默认标题",
            },
          ],
        },
      },
    },
  } as never);
  vi.mocked(onlineFormsApi.createRecord)
    .mockRejectedValueOnce({
      response: { data: { data: { title: ["不合法"] } } },
    })
    .mockResolvedValue({ data: { data: {} } } as never);
  const { wrapper } = await harness(Runtime);
  await wrapper.get("input").setValue("保留内容");
  const submit = () =>
    wrapper.findAll("button").find((b) => b.text() === "提交")!;
  await submit().trigger("click");
  await flushPromises();
  expect(wrapper.get("input").element.value).toBe("保留内容");
  await vi.waitFor(() => expect(wrapper.text()).toContain("不合法"));
  const key = vi.mocked(onlineFormsApi.createRecord).mock.calls[0]![2];
  await submit().trigger("click");
  await flushPromises();
  expect(vi.mocked(onlineFormsApi.createRecord).mock.calls[1]![2]).toBe(key);
  expect(wrapper.get("input").element.value).toBe("默认标题");
  expect(wrapper.text()).toContain("提交成功");
});

it("退出会话后迟到的加载响应不恢复敏感表单", async () => {
  let resolve!: (value: never) => void;
  vi.mocked(onlineFormsApi.published).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  const { wrapper, auth } = await harness(Runtime);
  auth.user = null;
  auth.token = "";
  await nextTick();
  resolve({ data: { data: { name: "不得恢复", definition } } } as never);
  await flushPromises();
  expect(wrapper.text()).not.toContain("不得恢复");
});

it("设计器试填使用当前未保存定义和服务端规则，不创建真实记录", async () => {
  const row = {
    id: "draft",
    name: "申请",
    code: "travel",
    status: "draft",
    version: 7,
    definition: {
      schema_version: 2,
      sections: [],
      rules: [],
      fields: [{ key: "title", label: "标题", type: "text", required: true }],
    },
  };
  vi.mocked(onlineFormsApi.list).mockResolvedValue({
    items: [row],
    pagination: { total: 1 },
  } as never);
  vi.mocked(onlineFormsApi.validate).mockResolvedValue({
    data: { data: { definition: row.definition } },
  } as never);
  const { wrapper } = await harness(Designer, "/online-forms");
  await wrapper.get("tbody tr").trigger("click");
  await flushPromises();
  await wrapper
    .findAll('[role="tab"]')
    .find((t) => t.text() === "实时预览")!
    .trigger("click");
  await nextTick();
  await wrapper.get('[aria-label="标题"]').setValue("试填内容");
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "试填校验")!
    .trigger("click");
  await flushPromises();
  expect(onlineFormsApi.validate).toHaveBeenCalledWith(
    expect.objectContaining({ schema_version: 2 }),
    { title: "试填内容" },
  );
  expect(onlineFormsApi.createRecord).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("试填校验通过，未写入记录");
  await wrapper.get('[aria-label="标题"]').setValue('校验后再修改');
  await nextTick();
  expect(wrapper.text()).not.toContain('试填校验通过，未写入记录');
});

it('只读用户可查看配置，但不能编辑、创建或调用管理员预览校验', async () => {
  vi.mocked(onlineFormsApi.list).mockResolvedValue({items:[{id:'draft',name:'只读申请',code:'readonly',status:'draft',version:1,definition}],pagination:{total:1}} as never);
  const {wrapper,auth}=await harness(Designer,'/online-forms');
  auth.user={...auth.user!,is_staff:false,permissions:['online_form:read']};
  await wrapper.get('tbody tr').trigger('click');await flushPromises();
  expect(wrapper.get('input').attributes('disabled')).toBeDefined();
  for (const text of ['新建草稿','保存草稿','发布','复制为新草稿','服务端校验']) expect(wrapper.findAll('button').find(b=>b.text()===text)!.attributes('disabled')).toBeDefined();
});
