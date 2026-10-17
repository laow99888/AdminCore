import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, ref, watch } from "vue";
import { createPinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus, { ElMessageBox } from "element-plus";
import request from "../src/api/request";
import { useAuthStore } from "../src/stores/auth";
import CodegenView from "../src/views/system/CodegenView.vue";
import GeneratedCrudPage from "../src/components/codegen/GeneratedCrudPage.vue";
import GeneratedFieldInput from "../src/components/codegen/GeneratedFieldInput.vue";
import type { GeneratedSchema } from "../src/components/codegen/types";

vi.mock("../src/i18n/uiText", () => ({
  uiText: (value: string) => value,
  registerUiMessages: vi.fn(),
}));
vi.mock("../src/api", () => ({
  newIdempotencyKey: () => "isolated-codegen-key",
}));
vi.mock("../src/api/request", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  errorMessage: (_value: unknown, fallback: string) => fallback,
  responseStatus: (value: { response?: { status: number } }) =>
    value.response?.status,
}));
vi.mock("../src/stores/modules", () => ({
  useModuleStore: () => ({ enabled: () => true, config: {} }),
}));
const Layout = defineComponent({
  template: '<main><slot name="header" /><slot /></main>',
});
const Dialog = defineComponent({
  name: "BaseDialog",
  props: ["modelValue", "confirmDisabled", "loading"],
  emits: ["confirm"],
  setup(props) {
    const rendered = ref(props.modelValue);
    watch(
      () => props.modelValue,
      (opened) => {
        if (opened) rendered.value = true;
      },
    );
    return { rendered };
  },
  // Element Plus 在关闭动画期间保留插槽，用同样的生命周期验收明细清理。
  template:
    '<section v-if="rendered" v-show="modelValue"><slot /><button :disabled="confirmDisabled || loading" @click="$emit(\'confirm\')">提交测试</button></section>',
});
const Table = defineComponent({
  name: "BaseTable",
  props: ["data", "total", "loading"],
  template: '<div><slot v-for="row in data" name="actions" :row="row" /></div>',
});
const Field = defineComponent({
  props: ["modelValue", "field"],
  emits: ["update:modelValue"],
  template:
    '<input :aria-label="field.label" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
});
const schema: GeneratedSchema = {
  schema_version: 2,
  module: "purchase_orders",
  title: "采购订单",
  model: "PurchaseOrder",
  structure: "master_detail",
  fields: [
    { name: "code", label: "编号", kind: "string", form: true, list: true },
    { name: "amount", label: "合计", kind: "decimal", form: false, list: true },
  ],
  details: [
    {
      name: "lines",
      label: "明细",
      model: "OrderLine",
      min_rows: 1,
      fields: [
        {
          name: "price",
          label: "单价",
          kind: "decimal",
          form: true,
          default: "0",
        },
      ],
    },
  ],
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(request.get).mockResolvedValue({
    data: { data: { items: [], pagination: { total: 0 } } },
  });
});
afterEach(() => localStorage.clear());
async function setup(
  component: typeof CodegenView | typeof GeneratedCrudPage,
  props = {},
) {
  const pinia = createPinia(),
    auth = useAuthStore(pinia);
  auth.token = "codegen-owner";
  auth.user = {
    id: "owner",
    username: "owner",
    email: "",
    avatar: "",
    is_staff: true,
    permissions: ["*"],
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: Layout }],
  });
  await router.push("/");
  const wrapper = mount(component, {
    props,
    global: {
      plugins: [pinia, router, ElementPlus],
      stubs: {
        AppLayout: Layout,
        BaseCard: Layout,
        BaseDialog: Dialog,
        BaseTable: Table,
        GeneratedFieldInput: Field,
      },
    },
  });
  return { wrapper, auth };
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll("button").find((value) => value.text() === text)!;
}

it("可视化配置预览后才能下载，修改字段会使旧预览失效", async () => {
  vi.mocked(request.post).mockResolvedValue({
    data: {
      definition: schema,
      files: [{ path: "models.py", content: "class Record: pass" }],
    },
  });
  const { wrapper } = await setup(CodegenView);
  expect(button(wrapper, "下载源码").attributes("disabled")).toBeDefined();
  await button(wrapper, "预览源码").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("class Record: pass");
  expect(button(wrapper, "下载源码").attributes("disabled")).toBeUndefined();
  await wrapper.find('input[aria-label="模块标题"]').setValue("新的标题");
  expect(button(wrapper, "下载源码").attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("配置已变化，请重新预览后下载");
  wrapper.unmount();
});

it("生成错误会保留配置并允许重试", async () => {
  vi.mocked(request.post).mockRejectedValue(new Error("bad schema"));
  const { wrapper } = await setup(CodegenView);
  await wrapper.find('input[aria-label="模块标题"]').setValue("需保留的配置");
  await button(wrapper, "预览源码").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("生成失败");
  expect(
    (wrapper.find('input[aria-label="模块标题"]').element as HTMLInputElement)
      .value,
  ).toBe("需保留的配置");
  expect(button(wrapper, "预览源码").attributes("disabled")).toBeUndefined();
  wrapper.unmount();
});

it("退出后晚到的源码响应不会恢复上一用户的业务定义", async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(request.post).mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const { wrapper, auth } = await setup(CodegenView);
  await button(wrapper, "预览源码").trigger("click");
  auth.user = null;
  auth.token = "";
  await flushPromises();
  resolve({
    data: {
      definition: schema,
      files: [{ path: "secret.py", content: "旧用户业务源码" }],
    },
  });
  await flushPromises();
  expect(wrapper.text()).not.toContain("旧用户业务源码");
  wrapper.unmount();
});

it("主子表提交保留十进制字符串并排除只读金额和明细ID", async () => {
  vi.mocked(request.post).mockResolvedValue({
    data: { data: { id: "created" } },
  });
  const { wrapper } = await setup(GeneratedCrudPage, { schema });
  await flushPromises();
  await button(wrapper, "新增").trigger("click");
  await flushPromises();
  await wrapper.find('input[aria-label="编号"]').setValue("PO-1");
  await wrapper.find('input[aria-label="单价"]').setValue("0.10");
  await button(wrapper, "提交测试").trigger("click");
  await flushPromises();
  expect(request.post).toHaveBeenCalledWith(
    "/purchase-orders/records/",
    { version: 0, code: "PO-1", lines: [{ price: "0.10" }] },
    { headers: { "Idempotency-Key": "isolated-codegen-key" } },
  );
  wrapper.unmount();
});

it("主子表编辑先读取详情，409保留本地明细并阻止重复保存", async () => {
  const row = { id: "order-1", version: 1, code: "PO-1", amount: "0.10" };
  vi.mocked(request.get).mockImplementation(async (url) => ({
    data: {
      data: String(url).endsWith("order-1/")
        ? { ...row, lines: [{ id: "server-line", price: "0.10" }] }
        : { items: [row], pagination: { total: 1 } },
    },
  }));
  vi.mocked(request.patch).mockRejectedValue({ response: { status: 409 } });
  const { wrapper } = await setup(GeneratedCrudPage, { schema });
  await flushPromises();
  await button(wrapper, "编辑").trigger("click");
  await flushPromises();
  expect(request.get).toHaveBeenCalledWith("/purchase-orders/records/order-1/");
  await wrapper.find('input[aria-label="单价"]').setValue("0.20");
  await button(wrapper, "提交测试").trigger("click");
  await flushPromises();
  expect(request.patch).toHaveBeenCalledWith(
    "/purchase-orders/records/order-1/",
    { version: 1, code: "PO-1", lines: [{ price: "0.20" }] },
  );
  expect(
    (wrapper.find('input[aria-label="单价"]').element as HTMLInputElement)
      .value,
  ).toBe("0.20");
  expect(button(wrapper, "提交测试").attributes("disabled")).toBeDefined();
  wrapper.unmount();
});

it("金额输入按字符串传递，避免0.1的浮点转换", async () => {
  const wrapper = mount(GeneratedFieldInput, {
    props: {
      field: { name: "price", label: "单价", kind: "decimal" },
      modelValue: "0.10",
      endpoint: "/orders/",
      fieldKey: "price",
      label: "单价",
    },
    global: { plugins: [createPinia(), ElementPlus] },
  });
  await wrapper.find("input").setValue("90071992547409.91");
  expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([
    "90071992547409.91",
  ]);
  wrapper.unmount();
});

it('审批业务的按钮遵守状态、所有者和权限，提交携带版本与稳定幂等键', async () => {
  const row = { id: 'order-1', creator: 'owner', version: 7, approval_status: 'draft', code: 'PO-1' };
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [row], pagination: { total: 1 } } } });
  // Element Plus 声明将 Action 与输入对象交叉；confirm 的实际返回值是动作字符串。
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never);
  vi.mocked(request.post).mockResolvedValue({ data: { data: row } });
  const { wrapper, auth } = await setup(GeneratedCrudPage, { schema: { ...schema, approval: { flow_code: 'purchase', title_field: 'code' } } });
  await flushPromises();
  await button(wrapper, '提交审批').trigger('click'); await flushPromises();
  expect(request.post).toHaveBeenCalledWith('/purchase-orders/records/order-1/submit/', { version: 7 }, { headers: { 'Idempotency-Key': 'purchase_orders-order-1-submit-7' } });
  auth.user!.permissions = ['purchase_orders:read']; await flushPromises();
  expect(button(wrapper, '提交审批')).toBeUndefined();
  wrapper.unmount();
});

it('待审批记录不能编辑删除，只提供撤回；失败显示可重试错误', async () => {
  const row = { id: 'order-1', creator: 'owner', version: 2, approval_status: 'pending', approval_request: 'application', code: 'PO-1' };
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [row], pagination: { total: 1 } } } });
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never);
  vi.mocked(request.post).mockRejectedValue({ response: { status: 409 } });
  const { wrapper } = await setup(GeneratedCrudPage, { schema: { ...schema, approval: { flow_code: 'purchase', title_field: 'code' } } });
  await flushPromises();
  expect(button(wrapper, '编辑')).toBeUndefined(); expect(button(wrapper, '删除')).toBeUndefined();
  expect(button(wrapper, '提交审批')).toBeUndefined();
  await button(wrapper, '撤回审批').trigger('click'); await flushPromises();
  expect(wrapper.text()).toContain('审批操作失败，请刷新记录后重试');
  expect(button(wrapper, '撤回审批').attributes('disabled')).toBeUndefined();
  wrapper.unmount();
});
