<template>
  <AppLayout
    ><BaseCard>
      <template #header
        ><div class="head">
          <h2>{{ uiText(schema.title) }}</h2>
          <BaseButton
            v-if="can('create')"
            variant="primary"
            :disabled="busy"
            @click="edit()"
            >{{ uiText("新增") }}</BaseButton
          >
        </div></template
      >
      <slot />
      <div v-if="schema.structure === 'tree'" class="tree-nav">
        <el-button :disabled="!parents.length || busy" @click="up">{{
          uiText("上一级")
        }}</el-button
        ><span
          >{{ uiText("当前父节点") }}：{{
            parents[parents.length - 1]?.label || uiText("根节点")
          }}</span
        >
      </div>
      <el-form class="filters" label-position="top" @submit.prevent="search">
        <template v-for="field in queryFields" :key="field.name"
          ><el-form-item :label="uiText(field.label)">
            <template v-if="field.query === 'range'"
              ><el-input
                v-model="filters[field.name + '_min']"
                :aria-label="uiText(field.label) + ' ' + uiText('最小值')"
                clearable /><el-input
                v-model="filters[field.name + '_max']"
                :aria-label="uiText(field.label) + ' ' + uiText('最大值')"
                clearable
            /></template>
            <el-select
              v-else-if="field.kind === 'enum' || field.kind === 'boolean'"
              v-model="filters[field.name]"
              :aria-label="uiText(field.label)"
              clearable
              ><el-option
                v-for="item in field.kind === 'enum'
                  ? field.choices
                  : [
                      { value: 'true', label: uiText('是') },
                      { value: 'false', label: uiText('否') },
                    ]"
                :key="item.value"
                :value="item.value"
                :label="uiText(item.label)"
            /></el-select>
            <GeneratedFieldInput
              v-else-if="
                ['relation', 'file', 'dictionary'].includes(field.kind)
              "
              :model-value="filters[field.name] ?? ''"
              :field="{ ...field, required: false }"
              :label="uiText(field.label)"
              :endpoint="endpoint"
              :field-key="field.name"
              @update:model-value="filters[field.name] = String($event ?? '')"
            />
            <el-input
              v-else
              v-model="filters[field.name]"
              :aria-label="uiText(field.label)"
              maxlength="200"
              clearable
              @keyup.enter="search"
            /> </el-form-item
        ></template>
        <el-button :disabled="loading || busy" @click="search">{{
          uiText("搜索")
        }}</el-button
        ><el-button :disabled="loading || busy" @click="resetFilters">{{
          uiText("重置")
        }}</el-button>
      </el-form>
      <el-alert
        v-if="listError"
        :title="uiText('列表加载失败，请刷新重试')"
        type="error"
        :closable="false"
      />
      <el-alert v-if="operationError" :title="operationError" type="error" :closable="false" role="alert" />
      <BaseTable
        :data="rows"
        :columns="columns"
        :loading="loading"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :action-width="schema.approval ? 420 : schema.structure === 'tree' ? 280 : 200"
        @update:current-page="changePage"
        @update:page-size="changeSize"
        @sort-change="sort"
      >
        <template #actions="{ row }"
          ><el-button
            v-if="schema.structure === 'tree'"
            link
            :disabled="busy"
            @click="down(row)"
            >{{ uiText("下级") }}</el-button
          ><el-button link :disabled="busy" @click="inspect(row)">{{
            uiText("详情")
          }}</el-button
          ><el-button
            v-if="can('update') && editable(row)"
            link
            :disabled="busy"
            @click="edit(row)"
            >{{ uiText("编辑") }}</el-button
          ><el-button
            v-if="can('delete') && editable(row) && !row.approval_request"
            link
            type="danger"
            :disabled="busy"
            @click="remove(row)"
            >{{ uiText("删除") }}</el-button
          ><el-button v-if="schema.approval && can('submit') && editable(row) && row.creator === auth.user?.id" link :disabled="busy" @click="approvalAction(row, 'submit')">{{ uiText('提交审批') }}</el-button>
          <el-button v-if="schema.approval && can('withdraw') && row.approval_status === 'pending' && row.creator === auth.user?.id" link :disabled="busy" @click="approvalAction(row, 'withdraw')">{{ uiText('撤回审批') }}</el-button>
          <el-button v-if="row.approval_request && modules.enabled('approvals')" link @click="router.push('/approvals')">{{ uiText('审批中心') }}</el-button>
          </template
        >
      </BaseTable>
    </BaseCard>
    <BaseDialog
      v-model="opened"
      :title="uiText(schema.title)"
      width="960px"
      :loading="saving"
      :confirm-disabled="conflict.active.value || readOnly"
      :before-close="guard.confirmDiscard"
      :confirm-text="uiText('保存')"
      @confirm="save"
    >
      <p v-if="error" role="alert">{{ error }}</p>
      <EditConflictPanel
        v-if="conflict.active.value"
        :loading="conflict.loading.value"
        :failed="conflict.failed.value"
        :disabled="saving"
        :version="form.version"
        :server-version="conflict.latest.value?.version"
        :rows="conflictRows"
        @inspect="conflict.inspect"
        @apply="conflict.applyLatest"
      />
      <el-form
        :disabled="saving || readOnly"
        label-position="top"
        @submit.prevent="save"
      >
        <div class="field-grid">
          <el-form-item
            v-for="field in formFields"
            :key="field.name"
            :label="uiText(field.label)"
            :required="field.required"
            ><GeneratedFieldInput
              v-model="form[field.name]"
              :field="field"
              :label="uiText(field.label)"
              :endpoint="endpoint"
              :field-key="field.name"
              :selected-label="form.display_labels?.[field.name]"
          /></el-form-item>
          <el-form-item
            v-if="schema.structure === 'tree'"
            :label="uiText('父节点')"
            ><GeneratedFieldInput
              v-model="form.parent"
              :field="parentField"
              :label="uiText('父节点')"
              :endpoint="endpoint"
              field-key="parent"
          /></el-form-item>
        </div>
        <section
          v-for="detail in schema.details"
          :key="detail.name"
          class="detail-group"
        >
          <div class="head">
            <h3>{{ uiText(detail.label) }}</h3>
            <el-button
              :disabled="form[detail.name].length >= (detail.max_rows ?? 100)"
              @click="addLine(detail)"
              >{{ uiText("添加明细") }}</el-button
            >
          </div>
          <p v-if="!form[detail.name].length">{{ uiText("暂无明细") }}</p>
          <div
            v-for="(line, index) in form[detail.name]"
            :key="index"
            class="detail-row"
          >
            <div class="head">
              <span>{{ uiText("明细") }} {{ Number(index) + 1 }}</span
              ><el-button
                :aria-label="uiText('删除明细') + ' ' + (Number(index) + 1)"
                :disabled="form[detail.name].length <= (detail.min_rows ?? 0)"
                @click="form[detail.name].splice(index, 1)"
                >{{ uiText("删除") }}</el-button
              >
            </div>
            <div class="field-grid">
              <el-form-item
                v-for="field in detail.fields.filter(
                  (item) => item.form !== false,
                )"
                :key="field.name"
                :label="uiText(field.label)"
                :required="field.required"
                ><GeneratedFieldInput
                  v-model="line[field.name]"
                  :field="field"
                  :label="
                    uiText(detail.label) +
                    ' ' +
                    (Number(index) + 1) +
                    ' ' +
                    uiText(field.label)
                  "
                  :endpoint="endpoint"
                  :field-key="detail.name + '.' + field.name"
                  :selected-label="line.display_labels?.[field.name]"
              /></el-form-item>
            </div>
          </div>
        </section>
      </el-form>
      <dl v-if="readOnly">
        <template
          v-for="field in schema.fields.filter((item) => item.form === false)"
          :key="field.name"
          ><dt>{{ uiText(field.label) }}</dt>
          <dd>{{ display(field, form[field.name]) }}</dd></template
        >
      </dl>
    </BaseDialog></AppLayout
  >
</template>
<script setup lang="ts">
import "./messages";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import { BaseButton, BaseCard, BaseDialog, BaseTable } from "@/components";
import AppLayout from "@/components/layout/AppLayout.vue";
import EditConflictPanel from "@/components/common/EditConflictPanel.vue";
import request, {
  type ApiResponse,
  type PagedData,
  responseStatus,
} from "@/api/request";
import { newIdempotencyKey } from "@/api";
import { useAuthStore } from "@/stores/auth";
import { useModuleStore } from "@/stores/modules";
import { useUnsavedChanges } from "@/composables/useUnsavedChanges";
import { useEditConflict } from "@/composables/useEditConflict";
import { uiText } from "@/i18n/uiText";
import { useRouter } from 'vue-router';
import GeneratedFieldInput from "./GeneratedFieldInput.vue";
import {
  defaultValues,
  type GeneratedDetail,
  type GeneratedField,
  type GeneratedSchema,
} from "./types";
const props = defineProps<{ schema: GeneratedSchema }>();
const router = useRouter();
const editable = (row: Row) => !props.schema.approval || ['draft', 'rejected', 'cancelled'].includes(row.approval_status);
const approvalLabel = (value: unknown) => uiText(({ draft: '草稿', pending: '审批中', approved: '已通过', rejected: '已驳回', cancelled: '已撤回' } as Record<string, string>)[String(value)] || String(value ?? ''));
// 业务字段由服务端生成的固定 schema 约束；表单需要同时保存标量和多组明细。
type Row = { id: string; version: number; [key: string]: any };
const auth = useAuthStore(),
  modules = useModuleStore(),
  resource = props.schema.module;
const endpoint = "/" + resource.replace(/_/g, "-") + "/records/";
const can = (action: string) =>
  modules.enabled(resource) && auth.can(resource + ":" + action);
const rows = ref<Row[]>([]),
  total = ref(0),
  page = ref(1),
  pageSize = ref(10),
  loading = ref(false),
  listError = ref(false);
const filters = reactive<Record<string, string>>({}),
  applied = ref<Record<string, string>>({}),
  ordering = ref((props.schema.ordering ?? []).join(","));
const parents = ref<{ id: string; label: string }[]>([]),
  opened = ref(false),
  saving = ref(false),
  removing = ref(false),
  fetching = ref(false),
  readOnly = ref(false),
  operationError = ref(''),
  error = ref("");
const form = reactive<Row>({ id: "", version: 0 }),
  busy = computed(
    () =>
      saving.value ||
      removing.value ||
      fetching.value ||
      conflict.loading.value,
  );
const formFields = computed(() =>
    props.schema.fields.filter((field) => field.form !== false),
  ),
  queryFields = computed(() =>
    props.schema.fields.filter(
      (field) => field.query && field.query !== "none",
    ),
  );
const parentField: GeneratedField = {
  name: "parent",
  label: "父节点",
  kind: "relation",
  required: false,
};
let generation = 0,
  detailGeneration = 0,
  key = "",
  submitted = "",
  controller: AbortController | undefined;
const guard = useUnsavedChanges({
  source: () => form,
  active: () => opened.value && !readOnly.value,
  busy: () => saving.value,
  canEdit: () => can(readOnly.value ? "read" : form.id ? "update" : "create"),
  clear: () => {
    opened.value = false;
    for (const name of Object.keys(form)) delete form[name];
    Object.assign(form, defaultValues(props.schema.fields), {
      id: "",
      version: 0,
      parent: null,
    });
    // 对话框关闭动画期间仍会渲染插槽，必须保留明细数组的结构。
    for (const detail of props.schema.details) form[detail.name] = [];
    error.value = "";
  },
});
const conflict = useEditConflict<Row>({
  identifier: () => (opened.value ? form.id : ""),
  current: guard.isCurrent,
  fetch: async (id, signal) =>
    (await request.get<ApiResponse<Row>>(endpoint + id + "/", { signal })).data
      .data,
  apply: (row) => {
    fill(row);
    guard.markClean();
  },
});
const conflictRows = computed(() =>
  props.schema.fields
    .map((field) => ({
      label: uiText(field.label),
      local: display(field, form[field.name]),
      server: display(field, conflict.latest.value?.[field.name]),
    }))
    .concat(
      props.schema.details.map((detail) => ({
        label: uiText(detail.label),
        local: JSON.stringify(form[detail.name]),
        server: JSON.stringify(conflict.latest.value?.[detail.name] ?? []),
      })),
    ),
);
function display(
  field: GeneratedField,
  value: unknown,
  labels?: Record<string, string>,
): string {
  if (
    ["relation", "file", "dictionary"].includes(field.kind) &&
    labels?.[field.name]
  )
    return labels[field.name]!;
  return field.kind === "boolean"
    ? uiText(value ? "是" : "否")
    : field.kind === "enum"
      ? uiText(
          field.choices?.find((item) => item.value === value)?.label ??
            String(value ?? ""),
        )
      : String(value ?? "");
}
const columns = computed(() =>
  props.schema.fields
    .filter((field) => field.list !== false)
    .map((field) => ({
      prop: field.name,
      label: uiText(field.label),
      width: 170,
      sortable: field.sortable ? ("custom" as const) : (false as const),
      render: (value: unknown, row: Row) =>
        display(field, value, row.display_labels),
    })).concat(props.schema.approval ? [{ prop: 'approval_status', label: uiText('审批状态'), width: 130, sortable: false, render: (value: unknown) => approvalLabel(value) }] : []),
);
function fill(row?: Row) {
  for (const name of Object.keys(form)) delete form[name];
  Object.assign(
    form,
    defaultValues(props.schema.fields),
    {
      id: "",
      version: 0,
      parent: parents.value[parents.value.length - 1]?.id ?? null,
    },
    row ? JSON.parse(JSON.stringify(row)) : {},
  );
  for (const detail of props.schema.details)
    form[detail.name] = row?.[detail.name]
      ? JSON.parse(JSON.stringify(row[detail.name]))
      : Array.from({ length: detail.min_rows ?? 0 }, () =>
          defaultValues(detail.fields),
        );
  key = newIdempotencyKey(resource);
  submitted = "";
  error.value = "";
}
async function load() {
  const current = ++generation;
  controller?.abort();
  controller = new AbortController();
  rows.value = [];
  total.value = 0;
  listError.value = false;
  if (!can("read") || !guard.isSessionCurrent()) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const response = await request.get<ApiResponse<PagedData<Row>>>(endpoint, {
      params: {
        ...applied.value,
        page: page.value,
        page_size: pageSize.value,
        ...(ordering.value ? { ordering: ordering.value } : {}),
        ...(props.schema.structure === "tree"
          ? { parent: parents.value[parents.value.length - 1]?.id ?? "root" }
          : {}),
      },
      signal: controller.signal,
    });
    if (current === generation && guard.isSessionCurrent() && can("read")) {
      rows.value = response.data.data.items;
      total.value = response.data.data.pagination.total;
    }
  } catch {
    if (current === generation && guard.isSessionCurrent())
      listError.value = true;
  } finally {
    if (current === generation) loading.value = false;
  }
}
function search() {
  applied.value = Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== ""),
  );
  page.value = 1;
  void load();
}
function resetFilters() {
  for (const name of Object.keys(filters)) delete filters[name];
  search();
}
function changePage(value: number) {
  page.value = value;
  void load();
}
function changeSize(value: number) {
  pageSize.value = value;
  page.value = 1;
  void load();
}
function sort(value: { prop: string; order: string | null }) {
  ordering.value = value.order
    ? (value.order === "descending" ? "-" : "") + value.prop
    : (props.schema.ordering ?? []).join(",");
  page.value = 1;
  void load();
}
function down(row: Row) {
  parents.value.push({
    id: row.id,
    label: String(
      row[
        props.schema.fields.find((field) => field.kind === "string")?.name ??
          "id"
      ],
    ),
  });
  page.value = 1;
  void load();
}
function up() {
  parents.value.pop();
  page.value = 1;
  void load();
}
function edit(row?: Row) {
  if (busy.value || !can(row ? "update" : "create")) return;
  if (row) {
    void openRow(row, false);
    return;
  }
  readOnly.value = false;
  fill();
  conflict.reset();
  opened.value = true;
}
function inspect(row: Row) {
  if (!busy.value && can("read")) void openRow(row, true);
}
async function openRow(row: Row, readonly: boolean) {
  const current = ++detailGeneration;
  fetching.value = true;
  try {
    const response = await request.get<ApiResponse<Row>>(
      endpoint + row.id + "/",
    );
    if (
      current !== detailGeneration ||
      !guard.isSessionCurrent() ||
      !can(readonly ? "read" : "update")
    )
      return;
    readOnly.value = readonly || !editable(response.data.data);
    fill(response.data.data);
    conflict.reset();
    opened.value = true;
  } catch {
    if (current === detailGeneration && guard.isSessionCurrent())
      listError.value = true;
  } finally {
    if (current === detailGeneration) fetching.value = false;
  }
}
function addLine(detail: GeneratedDetail) {
  form[detail.name].push(defaultValues(detail.fields));
}
function payload() {
  const value: Record<string, unknown> = { version: form.version };
  for (const field of formFields.value) value[field.name] = form[field.name];
  if (props.schema.structure === "tree") value.parent = form.parent;
  for (const detail of props.schema.details)
    value[detail.name] = form[detail.name].map(
      (line: Record<string, unknown>) =>
        Object.fromEntries(
          detail.fields
            .filter((field) => field.form !== false)
            .map((field) => [field.name, line[field.name]]),
        ),
    );
  return value;
}
async function save() {
  if (
    busy.value ||
    readOnly.value ||
    conflict.active.value ||
    !guard.isCurrent()
  )
    return;
  const values = payload(),
    digest = JSON.stringify(values);
  if (submitted && submitted !== digest) key = newIdempotencyKey(resource);
  submitted = digest;
  saving.value = true;
  error.value = "";
  try {
    if (form.id) await request.patch(endpoint + form.id + "/", values);
    else
      await request.post(endpoint, values, {
        headers: { "Idempotency-Key": key },
      });
    if (!guard.isCurrent()) return;
    guard.markClean();
    opened.value = false;
    await load();
  } catch (failure) {
    if (guard.isCurrent()) {
      if (responseStatus(failure) === 409 && form.id) conflict.mark();
      else
        error.value = uiText(
          "保存失败，输入已保留；请检查字段或关联选项后重试",
        );
    }
  } finally {
    saving.value = false;
  }
}
async function remove(row: Row) {
  if (busy.value || !can("delete") || !guard.isSessionCurrent()) return;
  removing.value = true;
  try {
    await ElMessageBox.confirm(uiText("确定删除？"), uiText("提示"));
    if (!can("delete") || !guard.isSessionCurrent()) return;
    await request.delete(endpoint + row.id + "/", {
      data: { version: row.version },
    });
    if (guard.isSessionCurrent()) {
      if (rows.value.length === 1 && page.value > 1) page.value--;
      await load();
    }
  } catch (failure) {
    if (failure !== "cancel" && failure !== "close" && guard.isSessionCurrent())
      listError.value = true;
  } finally {
    removing.value = false;
  }
}
async function approvalAction(row: Row, operation: 'submit' | 'withdraw') {
  if (busy.value || !can(operation) || !guard.isSessionCurrent()) return;
  removing.value = true;
  operationError.value = '';
  try {
    await ElMessageBox.confirm(uiText(operation === 'submit' ? '提交后将锁定业务内容，确定提交审批？' : '确定撤回审批？'), uiText('提示'));
    if (!can(operation) || !guard.isSessionCurrent()) return;
    await request.post(endpoint + row.id + '/' + operation + '/', { version: row.version }, {
      headers: { 'Idempotency-Key': `${resource}-${row.id}-${operation}-${row.version}` },
    });
    if (guard.isSessionCurrent()) await load();
  } catch (failure) {
    if (failure !== 'cancel' && failure !== 'close' && guard.isSessionCurrent()) operationError.value = uiText('审批操作失败，请刷新记录后重试');
  } finally { removing.value = false; }
}
watch(
  () => [
    auth.user?.id,
    auth.token,
    JSON.stringify(auth.user?.permissions),
    JSON.stringify(modules.config),
  ],
  () => {
    detailGeneration++;
    fetching.value = false;
    if (!can("read") || !guard.isSessionCurrent()) {
      opened.value = false;
      parents.value = [];
    }
    void load();
  },
);
onBeforeUnmount(() => {
  generation++;
  detailGeneration++;
  controller?.abort();
  rows.value = [];
});
void load();
</script>
<style scoped>
.head,
.tree-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
h2 {
  margin: 0;
  font-size: var(--font-size-lg);
}
.filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 12px;
  margin: 16px 0;
}
.filters .el-form-item {
  max-width: 220px;
  margin-bottom: 0;
}
.filters .el-form-item :deep(.el-form-item__content) {
  display: grid;
  gap: 4px;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.detail-row {
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-md);
  padding: 12px;
  margin: 12px 0;
}
.detail-group {
  margin-top: 16px;
}
.tree-nav {
  margin-top: 16px;
  justify-content: flex-start;
}
p[role="alert"] {
  color: var(--el-color-danger);
}
dd {
  overflow-wrap: anywhere;
}
@media (max-width: 640px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .filters .el-form-item {
    max-width: none;
    width: 100%;
  }
  .head {
    align-items: flex-start;
  }
}
</style>
