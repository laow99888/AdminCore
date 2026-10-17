<template>
  <AppLayout
    ><div class="page">
      <BaseCard
        ><template #header
          ><div class="head">
            <div>
              <h2>{{ uiText("代码生成器") }}</h2>
              <p>
                {{ uiText("配置业务结构，预览前后端源码，再下载接入项目") }}
              </p>
            </div>
            <div class="actions">
              <el-button :disabled="busy" @click="exportDefinition">{{
                uiText("导出定义")
              }}</el-button
              ><el-button :disabled="busy" @click="importOpen = true">{{
                uiText("导入定义")
              }}</el-button
              ><el-button
                type="primary"
                :loading="previewing"
                :disabled="busy"
                @click="preview"
                >{{ uiText("预览源码") }}</el-button
              ><el-button
                :loading="downloading"
                :disabled="busy || !previewCurrent"
                @click="download"
                >{{ uiText("下载源码") }}</el-button
              >
            </div>
          </div></template
        >
        <el-alert
          :title="
            uiText(
              '下载后需审查模型和迁移并显式注册模块；服务器不会自动安装或执行源码',
            )
          "
          type="info"
          :closable="false"
        />
        <p v-if="error" role="alert" tabindex="-1" class="error">{{ error }}</p>
        <el-tabs v-model="tab"
          ><el-tab-pane :label="uiText('业务配置')" name="config">
            <el-form label-position="top" :disabled="busy"
              ><div class="identity">
                <el-form-item :label="uiText('模块标识')" required
                  ><el-input
                    v-model="schema.module"
                    maxlength="20"
                    :aria-label="uiText('模块标识')" /></el-form-item
                ><el-form-item :label="uiText('模块标题')" required
                  ><el-input
                    v-model="schema.title"
                    maxlength="40"
                    :aria-label="uiText('模块标题')" /></el-form-item
                ><el-form-item :label="uiText('模型名称')" required
                  ><el-input
                    v-model="schema.model"
                    maxlength="48"
                    :aria-label="uiText('模型名称')" /></el-form-item
                ><el-form-item :label="uiText('业务结构')"
                  ><el-select
                    v-model="schema.structure"
                    :aria-label="uiText('业务结构')"
                    ><el-option
                      value="single"
                      :label="uiText('单表')" /><el-option
                      value="tree"
                      :label="uiText('树表')" /><el-option
                      value="master_detail"
                      :label="uiText('主子表')" /></el-select></el-form-item
                ><el-form-item :label="uiText('默认排序')"
                  ><el-input
                    v-model="ordering"
                    :aria-label="uiText('默认排序')"
                /></el-form-item></div
            ></el-form>
            <FieldConfigEditor v-model="schema.fields" :disabled="busy" />
            <el-form label-position="top" :disabled="busy">
              <el-form-item :label="uiText('接入审批')"><el-switch :model-value="!!schema.approval" :aria-label="uiText('接入审批')" @update:model-value="schema.approval = $event ? { flow_code: '', title_field: schema.fields.find(f => f.kind === 'string')?.name || '' } : undefined" /></el-form-item>
              <template v-if="schema.approval"><div class="identity">
                <el-form-item :label="uiText('审批流程编码')" required><el-input v-model="schema.approval.flow_code" :aria-label="uiText('审批流程编码')" maxlength="80" /></el-form-item>
                <el-form-item :label="uiText('业务标题字段')" required><el-select v-model="schema.approval.title_field" :aria-label="uiText('业务标题字段')"><el-option v-for="field in schema.fields.filter(f => f.kind === 'string')" :key="field.name" :value="field.name" :label="field.label" /></el-select></el-form-item>
              </div><p>{{ uiText('提交后锁定内容；通过后保持只读；驳回或撤回后可编辑再提交') }}</p></template>
              <el-form-item :label="uiText('接入报表')"><el-switch :model-value="!!schema.reports" :aria-label="uiText('接入报表')" @update:model-value="schema.reports = $event ? { dimensions: [], metrics: [], filters: [] } : undefined" /></el-form-item>
              <div v-if="schema.reports" class="identity">
                <el-form-item v-for="key in (['dimensions', 'metrics', 'filters'] as const)" :key="key" :label="uiText({ dimensions: '报表维度', metrics: '报表指标', filters: '报表筛选' }[key])">
                  <el-select v-model="schema.reports[key]" multiple :aria-label="uiText({ dimensions: '报表维度', metrics: '报表指标', filters: '报表筛选' }[key])">
                    <el-option v-for="field in reportFields(key)" :key="field.name" :value="field.name" :label="field.label" />
                  </el-select>
                </el-form-item>
              </div>
            </el-form>
            <template v-if="schema.structure === 'master_detail'"
              ><div class="head">
                <h3>{{ uiText("明细分组") }}</h3>
                <el-button
                  :disabled="busy || schema.details.length >= 5"
                  @click="addDetail"
                  >{{ uiText("添加明细组") }}</el-button
                >
              </div>
              <el-empty
                v-if="!schema.details.length"
                :description="uiText('主子表至少需要一组明细')" />
              <section
                v-for="(detail, index) in schema.details"
                :key="index"
                class="detail"
              >
                <div class="head">
                  <h3>{{ detail.label }}</h3>
                  <el-button
                    :disabled="busy"
                    type="danger"
                    plain
                    @click="schema.details.splice(index, 1)"
                    >{{ uiText("删除明细组") }}</el-button
                  >
                </div>
                <el-form :disabled="busy" label-position="top"
                  ><div class="identity">
                    <el-form-item :label="uiText('明细标识')"
                      ><el-input
                        v-model="detail.name"
                        :aria-label="uiText('明细标识')" /></el-form-item
                    ><el-form-item :label="uiText('明细标题')"
                      ><el-input
                        v-model="detail.label"
                        :aria-label="uiText('明细标题')" /></el-form-item
                    ><el-form-item :label="uiText('明细模型')"
                      ><el-input
                        v-model="detail.model"
                        :aria-label="uiText('明细模型')" /></el-form-item
                    ><el-form-item :label="uiText('最少行数')"
                      ><el-input-number
                        v-model="detail.min_rows"
                        :min="0"
                        :max="200"
                        :precision="0"
                        :aria-label="uiText('最少行数')" /></el-form-item
                    ><el-form-item :label="uiText('最多行数')"
                      ><el-input-number
                        v-model="detail.max_rows"
                        :min="1"
                        :max="200"
                        :precision="0"
                        :aria-label="uiText('最多行数')"
                    /></el-form-item></div></el-form
                ><FieldConfigEditor
                  v-model="detail.fields"
                  :disabled="busy"
                  detail
                /></section
            ></template> </el-tab-pane
          ><el-tab-pane :label="uiText('源码预览')" name="preview"
            ><el-empty
              v-if="!files.length"
              :description="uiText('配置业务结构后点击预览源码')"
            /><template v-else
              ><el-alert
                v-if="!previewCurrent"
                :title="uiText('配置已变化，请重新预览后下载')"
                type="warning"
                :closable="false"
              />
              <div class="source-layout">
                <el-select
                  v-model="selected"
                  :aria-label="uiText('源码文件')"
                  filterable
                  ><el-option
                    v-for="file in files"
                    :key="file.path"
                    :value="file.path"
                    :label="file.path"
                /></el-select>
                <pre tabindex="0" :aria-label="uiText('源码内容')">{{
                  files.find((file) => file.path === selected)?.content
                }}</pre>
              </div></template
            ></el-tab-pane
          ></el-tabs
        >
      </BaseCard>
    </div>
    <BaseDialog
      v-model="importOpen"
      :title="uiText('导入业务定义')"
      width="800px"
      :confirm-text="uiText('导入')"
      @confirm="importDefinition"
      ><el-input
        v-model="importText"
        type="textarea"
        :rows="16"
        maxlength="131072"
        :aria-label="uiText('业务定义JSON')"
      />
      <p v-if="importError" role="alert" class="error">
        {{ importError }}
      </p></BaseDialog
    ></AppLayout
  >
</template>
<script setup lang="ts">
import "@/components/codegen/messages";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { BaseCard, BaseDialog } from "@/components";
import AppLayout from "@/components/layout/AppLayout.vue";
import FieldConfigEditor from "@/components/codegen/FieldConfigEditor.vue";
import { newField, type GeneratedSchema } from "@/components/codegen/types";
import request, { errorMessage } from "@/api/request";
import { useAuthStore } from "@/stores/auth";
import { useModuleStore } from "@/stores/modules";
import { useUnsavedChanges } from "@/composables/useUnsavedChanges";
import { useErrorSummary } from "@/composables/useErrorSummary";
import { uiText } from "@/i18n/uiText";
const initial = (): GeneratedSchema => ({
  schema_version: 2,
  module: "business_items",
  title: "业务记录",
  model: "BusinessItem",
  structure: "single",
  fields: [{ ...newField(), name: "name", label: "名称", query: "contains" }],
  details: [],
});
const schema = reactive<GeneratedSchema>(initial()),
  ordering = ref("-created_at,-id"),
  tab = ref("config"),
  previewing = ref(false),
  downloading = ref(false),
  importing = ref(false),
  error = ref("");
const importOpen = ref(false),
  importText = ref(""),
  importError = ref(""),
  files = ref<{ path: string; content: string }[]>([]),
  selected = ref(""),
  previewFingerprint = ref("");
const busy = computed(
    () => previewing.value || downloading.value || importing.value,
  ),
  auth = useAuthStore(),
  modules = useModuleStore();
const definition = computed(() => ({
  ...schema,
  details: schema.structure === "master_detail" ? schema.details : [],
  ordering: ordering.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean),
}));
const fingerprint = computed(() => JSON.stringify(definition.value)),
  previewCurrent = computed(
    () =>
      !!files.value.length && previewFingerprint.value === fingerprint.value,
  );
let generation = 0,
  controller: AbortController | undefined;
const guard = useUnsavedChanges({
  source: () => definition.value,
  busy: () => busy.value,
  canEdit: () =>
    modules.enabled("system") &&
    !!(auth.user?.is_staff || auth.user?.is_superuser) &&
    auth.can("codegen:generate"),
  clear: () => {
    generation++;
    controller?.abort();
    previewing.value = false;
    downloading.value = false;
    importing.value = false;
    delete schema.approval; delete schema.reports;
    Object.assign(schema, initial());
    ordering.value = "-created_at,-id";
    files.value = [];
    previewFingerprint.value = "";
    selected.value = "";
    importText.value = "";
    importOpen.value = false;
    error.value = "";
  },
});
useErrorSummary(error);
function addDetail() {
  let index = schema.details.length + 1;
  while (schema.details.some((item) => item.name === `lines_${index}`)) index++;
  schema.details.push({
    name: `lines_${index}`,
    label: "业务明细",
    model: `${schema.model}Line${index}`,
    min_rows: 0,
    max_rows: 100,
    fields: [newField()],
  });
}
function reportFields(key: 'dimensions' | 'metrics' | 'filters') {
  const kinds = key === 'metrics' ? ['integer', 'decimal'] : key === 'dimensions' ? ['string', 'enum', 'dictionary', 'boolean', 'date', 'datetime'] : ['string', 'enum', 'dictionary', 'boolean', 'date', 'datetime', 'integer', 'decimal'];
  return [...schema.fields.filter(field => kinds.includes(field.kind)), ...(key !== 'metrics' ? [{ name: 'created_at', label: uiText('创建时间') }, ...(schema.approval ? [{ name: 'approval_status', label: uiText('审批状态') }] : [])] : [])];
}
async function preview() {
  if (busy.value || !guard.isCurrent()) return;
  const submitted = fingerprint.value,
    current = ++generation;
  controller?.abort();
  controller = new AbortController();
  previewing.value = true;
  error.value = "";
  try {
    const response = await request.post<{
      definition: GeneratedSchema;
      files: { path: string; content: string }[];
    }>(
      "/system/codegen/preview/",
      { definition: definition.value },
      { signal: controller.signal },
    );
    if (current !== generation || !guard.isCurrent()) return;
    files.value = response.data.files;
    selected.value =
      files.value.find((file) => file.path.endsWith("/models.py"))?.path ??
      files.value[0]?.path ??
      "";
    previewFingerprint.value = submitted;
    tab.value = "preview";
  } catch (failure) {
    if (current === generation && guard.isCurrent())
      error.value = errorMessage(
        failure,
        uiText("生成失败，请检查字段、关系、默认值及唯一名称"),
      );
  } finally {
    if (current === generation) previewing.value = false;
  }
}
function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}
async function download() {
  if (busy.value || !previewCurrent.value || !guard.isCurrent()) return;
  downloading.value = true;
  error.value = "";
  const submitted = fingerprint.value;
  try {
    const response = await request.post<Blob>(
      "/system/codegen/download/",
      { definition: definition.value },
      { responseType: "blob" },
    );
    if (!guard.isCurrent() || submitted !== fingerprint.value) return;
    saveBlob(response.data, `${schema.module}-source.zip`);
    guard.markClean();
  } catch {
    if (guard.isCurrent()) error.value = uiText("源码下载失败，请重试");
  } finally {
    downloading.value = false;
  }
}
function exportDefinition() {
  saveBlob(
    new Blob([JSON.stringify(definition.value, null, 2)], {
      type: "application/json",
    }),
    `${schema.module}-definition.json`,
  );
  guard.markClean();
}
async function importDefinition() {
  if (busy.value || !guard.isCurrent()) return;
  importError.value = "";
  const current = ++generation;
  try {
    const value: unknown = JSON.parse(importText.value);
    if (
      !value ||
      typeof value !== "object" ||
      !("schema_version" in value) ||
      value.schema_version !== 2 ||
      !("fields" in value) ||
      !Array.isArray(value.fields) ||
      !("module" in value) ||
      typeof value.module !== "string"
    )
      throw new Error();
    if (!(await guard.confirmDiscard()) || !guard.isCurrent()) return;
    importing.value = true;
    const response = await request.post<{
      definition: GeneratedSchema;
      files: { path: string; content: string }[];
    }>("/system/codegen/preview/", { definition: value });
    if (current !== generation || !guard.isCurrent()) return;
    delete schema.approval; delete schema.reports;
    Object.assign(schema, response.data.definition);
    ordering.value = (response.data.definition.ordering ?? []).join(",");
    files.value = [];
    importOpen.value = false;
    importText.value = "";
    previewFingerprint.value = "";
  } catch {
    if (current === generation && guard.isCurrent())
      importError.value = uiText("导入失败，请提供有效的V2业务定义");
  } finally {
    if (current === generation) importing.value = false;
  }
}
onBeforeUnmount(() => {
  generation++;
  controller?.abort();
});
</script>
<style scoped>
.page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.head,
.actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.head {
  justify-content: space-between;
}
h2 {
  font-size: var(--font-size-lg);
  margin: 0;
}
.head p {
  color: var(--el-text-color-secondary);
  margin-bottom: 0;
}
.identity {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 16px;
  margin-top: 16px;
}
.detail {
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  margin: 12px 0;
}
.source-layout {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  min-width: 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--color-bg-elevated);
  padding: 16px;
  max-height: 60vh;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  border-radius: var(--radius-md);
}
.error {
  color: var(--el-color-danger);
}
:deep(.el-select) {
  width: 100%;
}
@media (max-width: 768px) {
  .identity {
    grid-template-columns: minmax(0, 1fr);
  }
  .actions {
    width: 100%;
  }
  .actions :deep(button) {
    margin-left: 0;
    min-height: 44px;
  }
  .detail {
    padding: 12px;
  }
}
</style>
