<template>
  <AppLayout
    ><div class="page">
      <EditConflictPanel v-if="conflict.active.value" :loading="conflict.loading.value" :failed="conflict.failed.value" :version="editing?.version ?? 0" :server-version="conflict.latest.value?.version" :rows="conflictRows" @inspect="conflict.inspect" @apply="conflict.applyLatest" />
      <BaseCard
        ><template #header
          ><div class="head">
            <div>
              <h2>{{ uiText("在线表单设计器") }}</h2>
              <p>
                {{ uiText("草稿可编辑，发布后版本固定；运行时只接受登记字段") }}
              </p>
            </div>
            <div class="actions">
              <BaseButton :disabled="saving || !canCreate" @click="newForm">{{
                uiText("新建草稿")
              }}</BaseButton>
              <BaseButton
                variant="primary"
                :disabled="!editing || locked"
                @click="save"
                >{{ uiText("保存草稿") }}</BaseButton
              >
              <BaseButton
                v-if="editing?.status === 'draft'"
                variant="primary"
                :disabled="saving || !canPublish"
                @click="publish"
                >{{ uiText("发布") }}</BaseButton
              >
            </div>
          </div></template
        >
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
        <el-table :data="forms" stripe @row-click="select"
          ><el-table-column
            prop="name"
            :label="uiText('名称')"
            min-width="120" /><el-table-column
            prop="code"
            :label="uiText('编码')"
            min-width="120" /><el-table-column
            prop="release_number"
            :label="uiText('发布版本')"
            width="100" /><el-table-column
            prop="status"
            :label="uiText('状态')"
            width="100"
        /></el-table>
        <el-pagination
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          layout="prev, pager, next, total"
          :disabled="saving"
          @current-change="load"
        />
      </BaseCard>
      <BaseCard v-if="editing">
        <div class="actions editor-actions">
          <el-button
            :disabled="saving || !canValidate"
            @click="exportDefinition"
            >{{ uiText("导出定义") }}</el-button
          ><el-button :disabled="locked" @click="importOpen = true">{{
            uiText("导入定义")
          }}</el-button
          ><el-button :disabled="saving || !canCreate" @click="copyDraft">{{
            uiText("复制为新草稿")
          }}</el-button
          ><el-button v-if="editing.id && editing.status !== 'draft'" :disabled="saving || !canCreate" @click="createNextVersion">{{ uiText('创建下一版') }}</el-button
          ><el-button
            :disabled="saving || !canValidate"
            @click="checkDefinition"
            >{{ uiText("服务端校验") }}</el-button
          >
        </div>
        <el-tabs v-model="tab"
          ><el-tab-pane :label="uiText('表单配置')" name="design">
            <el-form label-position="top" :disabled="locked">
              <div class="identity">
                <el-form-item :label="uiText('名称')"
                  ><el-input
                    v-model="editing.name"
                    :maxlength="120" /></el-form-item
                ><el-form-item :label="uiText('编码')"
                  ><el-input v-model="editing.code" :disabled="!!editing.id" :maxlength="64"
                /></el-form-item>
              </div>
              <el-form-item :label="uiText('审批流程（可选）')">
                <el-select v-model="editing.approval_flow_code" clearable :loading="flowsLoading" :aria-label="uiText('审批流程（可选）')" @visible-change="loadFlows">
                  <el-option v-if="editing.approval_flow_code && !flowChoices.some(item => item.code === editing!.approval_flow_code)" :value="editing.approval_flow_code" :label="editing.approval_flow_code" />
                  <el-option v-for="flow in flowChoices" :key="flow.code" :value="flow.code" :label="`${flow.name} (${flow.code}) · ${flow.revision}`" />
                </el-select>
                <p class="hint">{{ uiText('发布时固定流程版本；只有同名且类型一致的顶层字段可作为流程输入。留空不启用审批。') }}</p>
                <p v-if="flowsError" role="alert">{{ flowsError }}</p>
              </el-form-item>
              <h3>{{ uiText("分组与布局") }}</h3>
              <p class="hint">
                {{ uiText("桌面最多两列，手机自动单列；隐藏字段不会保存") }}
              </p>
              <div
                v-for="(section, index) in editing.definition.sections"
                :key="index"
                class="section-row"
              >
                <el-input
                  v-model="section.key"
                  :aria-label="uiText('分组标识')"
                  :maxlength="40"
                /><el-input
                  v-model="section.title"
                  :aria-label="uiText('分组标题')"
                  :maxlength="120"
                /><el-button @click="removeSection(index)">{{
                  uiText("删除分组")
                }}</el-button>
              </div>
              <el-button
                :disabled="locked || (editing.definition.sections?.length || 0) >= 20"
                @click="addSection"
                >{{ uiText("添加分组") }}</el-button
              >
              <h3>{{ uiText("字段") }}</h3>
              <FieldDesigner
                v-model="editing.definition.fields"
                :sections="editing.definition.sections"
              />
              <h3>{{ uiText("跨字段校验") }}</h3>
              <ComparisonEditor
                :model-value="editing.definition.rules || []"
                :fields="editing.definition.fields"
                @update:model-value="editing.definition.rules = $event"
              />
            </el-form> </el-tab-pane
          ><el-tab-pane :label="uiText('实时预览')" name="preview">
            <el-alert
              :title="uiText('预览不会保存记录；试填校验使用服务端规则')"
              type="info"
              :closable="false"
            />
            <OnlineFormRenderer
              v-model="previewValues"
              :definition="editing.definition"
              :errors="previewErrors"
              :disabled="saving"
              :attachment-context="editing.id ? { code: editing.code, formId: editing.id } : undefined"
            />
            <div class="actions">
              <el-button
                type="primary"
                :loading="saving"
                :disabled="!canValidate"
                @click="validatePreview"
                >{{ uiText("试填校验") }}</el-button
              ><el-button :disabled="saving" @click="resetPreview">{{
                uiText("重置试填")
              }}</el-button>
            </div>
            <el-alert
              v-if="previewSuccess"
              :title="uiText('试填校验通过，未写入记录')"
              type="success"
              :closable="false"
            /> </el-tab-pane
        ></el-tabs>
        <p v-if="feedback" class="feedback" role="status">{{ feedback }}</p>
        <p v-if="formError" class="failure" role="alert">{{ formError }}</p>
        <div v-if="editing.id" class="runtime-link">
          <router-link :to="`/online-forms/${editing.code}`">{{
            uiText("打开填写页面")
          }}</router-link>
        </div>
      </BaseCard>
      <el-dialog
        v-model="importOpen"
        :title="uiText('导入表单定义')"
        width="min(700px, 94vw)"
        :close-on-click-modal="false"
      >
        <el-input
          v-model="importText"
          type="textarea"
          :rows="14"
          :maxlength="131072"
          :aria-label="uiText('表单定义 JSON')"
        />
        <p v-if="importError" class="failure" role="alert">{{ importError }}</p>
        <template #footer
          ><el-button :disabled="saving" @click="importOpen = false">{{
            uiText("取消")
          }}</el-button
          ><el-button
            type="primary"
            :loading="saving"
            @click="importDefinition"
            >{{ uiText("校验并导入") }}</el-button
          ></template
        >
      </el-dialog>
    </div></AppLayout
  >
</template>
<script setup lang="ts">
import EditConflictPanel from '@/components/common/EditConflictPanel.vue'
import { useEditConflict } from '@/composables/useEditConflict'
import { responseStatus } from '@/api/request'
import "@/components/onlineForms/messages";
import "@/components/onlineForms/lifecycleMessages";
import { computed, onMounted, ref, watch } from "vue";
import { useUnsavedChanges } from "@/composables/useUnsavedChanges";
import { useLatestRead } from "@/composables/useLatestRead";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenants";
import { errorMessage, notifyError } from "@/api/request";
import { ElMessage } from "element-plus";
import AppLayout from "@/components/layout/AppLayout.vue";
import { BaseButton, BaseCard } from "@/components";
import {
  onlineFormsApi,
  type OnlineFormDefinition,
  type OnlineFormRow,
} from "@/api";
import { uiText } from "@/i18n/uiText";
import FieldDesigner from "@/components/onlineForms/FieldDesigner.vue";
import ComparisonEditor from "@/components/onlineForms/ComparisonEditor.vue";
import OnlineFormRenderer from "@/components/onlineForms/OnlineFormRenderer.vue";
import { onlineFormAttachmentsApi } from '@/api/onlineFormAttachments';
import { onlineFormLifecycleApi, type ReleasedOnlineForm } from '@/api/onlineFormLifecycle';
import {
  submissionValues,
  fieldErrors,
  initialValues,
  upgrade,
  type FormValues,
} from "@/components/onlineForms/runtime";
const forms = ref<OnlineFormRow[]>([]),
  editing = ref<ReleasedOnlineForm | null>(null),
  saving = ref(false),
  error = ref("");
const flowChoices = ref<{ code: string; name: string; revision: number }[]>([]), flowsLoading = ref(false), flowsError = ref('');
async function loadFlows(visible: boolean) {
  if (!visible || locked.value || !editing.value) return;
  const epoch = context, owner = editing.value;
  flowsLoading.value = true; flowsError.value = ''; flowChoices.value = [];
  try {
    const rows = await onlineFormLifecycleApi.approvalFlows(owner.id || undefined);
    if (currentSession(epoch) && editing.value === owner) flowChoices.value = rows;
  } catch (err) { if (currentSession(epoch) && editing.value === owner) flowsError.value = errorMessage(err, uiText('审批流程加载失败')); }
  finally { if (currentSession(epoch) && editing.value === owner) flowsLoading.value = false; }
}
const tab = ref("design"),
  feedback = ref(""),
  formError = ref(""),
  previewValues = ref<FormValues>({}),
  previewErrors = ref<Record<string, string>>({}),
  previewSuccess = ref(false);
const importOpen = ref(false),
  importText = ref(""),
  importError = ref("");
const auth = useAuthStore();
const tenants = useTenantStore();
let context = 0;
const currentSession = (epoch: number) => epoch === context && guard.isSessionCurrent();
const admin = computed(
  () => !!(auth.user?.is_staff || auth.user?.is_superuser),
);
const canCreate = computed(() => admin.value && auth.can("online_form:create"));
const canUpdate = computed(() => admin.value && auth.can("online_form:update"));
const canPublish = computed(
  () => admin.value && auth.can("online_form:publish"),
);
const canValidate = computed(() => admin.value && auth.can("online_form:read"));
const page = ref(1),
  total = ref(0),
  locked = computed(
    () =>
      editing.value?.status !== "draft" ||
      saving.value ||
      !(editing.value?.id ? canUpdate.value : canCreate.value),
  );
const beginRead = useLatestRead(() => {
  forms.value = [];
  total.value = 0;
});
const guard = useUnsavedChanges({
  source: () => (editing.value?.status === "draft" ? editing.value : null),
  busy: () => saving.value,
  clear: () => {
    editing.value = null;
    previewValues.value = {};
    importText.value = "";
    importOpen.value = false;
  },
});
watch(previewValues, () => {
  previewErrors.value = {};
  previewSuccess.value = false;
}, {deep: true, flush: 'sync'});
function resetPreview() {
  previewValues.value = initialValues(editing.value?.definition.fields || []);
  previewErrors.value = {};
  previewSuccess.value = false;
}
watch(
  () => editing.value?.definition,
  () => {
    previewErrors.value = {};
    previewSuccess.value = false;
    feedback.value = "";
  },
  { deep: true },
);
const conflict = useEditConflict<OnlineFormRow>({ identifier: () => editing.value?.id || '', current: () => guard.isSessionCurrent(), fetch: onlineFormsApi.detail, apply: loadEditor })
const conflictRows = computed(() => conflict.latest.value ? [{ label: uiText('定义'), local: JSON.stringify(editing.value), server: JSON.stringify(conflict.latest.value) }] : [])
function loadEditor(row: OnlineFormRow) {
  conflict.reset()
  flowChoices.value = []; flowsError.value = ''; flowsLoading.value = false;
  editing.value = JSON.parse(JSON.stringify(row));
  if (editing.value) editing.value.definition = upgrade(row.definition);
  formError.value = "";
  feedback.value = "";
  resetPreview();
  guard.markClean();
}
async function select(row: OnlineFormRow) {
  const epoch = context;
  if (!saving.value && (await guard.confirmDiscard()) && currentSession(epoch)) loadEditor(row);
}
async function newForm() {
  const epoch = context;
  if (saving.value || !canCreate.value || !(await guard.confirmDiscard()) || !currentSession(epoch))
    return;
  loadEditor({
    id: "",
    name: "",
    code: "",
    status: "draft",
    version: 1,
    definition: {
      schema_version: 2,
      sections: [],
      rules: [],
      fields: [
        {
          key: "title",
          label: uiText("标题"),
          type: "text",
          required: true,
          max_length: 200,
        },
      ],
    },
  });
}
async function copyDraft() {
  const epoch = context;
  if (
    !editing.value ||
    saving.value ||
    !canCreate.value ||
    !(await guard.confirmDiscard()) || !currentSession(epoch)
  )
    return;
  const row = {
    ...editing.value,
    id: "",
    name: `${editing.value.name} ${uiText("副本")}`,
    code: "",
    status: "draft" as const,
    version: 1,
  };
  loadEditor(row);
}
async function createNextVersion() {
  const epoch = context;
  if (!editing.value?.id || editing.value.status === 'draft' || saving.value || !canCreate.value) return;
  saving.value = true;
  formError.value = '';
  try {
    const row = await onlineFormLifecycleApi.newVersion(editing.value.id, editing.value.version);
    if (!currentSession(epoch)) return;
    loadEditor(row);
    await load();
    ElMessage.success(uiText('新版草稿已创建'));
  } catch (err) {
    if (currentSession(epoch)) formError.value = errorMessage(err, uiText('保存失败'));
  } finally { saving.value = false; }
}
function addSection() {
  editing.value?.definition.sections?.push({
    key: `section_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`,
    title: uiText("新分组"),
  });
}
function removeSection(index: number) {
  const sections = editing.value?.definition.sections;
  const key = sections?.[index]?.key;
  if (!sections || !editing.value) return;
  sections.splice(index, 1);
  for (const field of editing.value.definition.fields)
    if (field.section === key) field.section = "";
}
async function load() {
  const current = beginRead();
  try {
    const data = await onlineFormsApi.list({ page: page.value, page_size: 20 });
    if (current()) {
      forms.value = data.items;
      total.value = data.pagination.total;
      error.value = "";
    }
  } catch (err) {
    if (current()) error.value = errorMessage(err, uiText("列表加载失败"));
  }
}
async function save(): Promise<boolean> {
  const epoch = context;
  if (conflict.active.value || !editing.value || locked.value) return false;
  saving.value = true;
  formError.value = "";
  try {
    const payload = {
      name: editing.value.name,
      code: editing.value.code,
      definition: editing.value.definition,
      version: editing.value.version,
      approval_flow_code: editing.value.approval_flow_code || '',
    };
    const response = editing.value.id
      ? await onlineFormsApi.update(editing.value.id, payload)
      : await onlineFormsApi.create(payload);
    if (!currentSession(epoch)) return false;
    loadEditor(response.data.data || response.data);
    await load();
    ElMessage.success(uiText("表单草稿已保存"));
    return true;
  } catch (err) {
    if (!currentSession(epoch)) return false;
    if (responseStatus(err) === 409 && editing.value?.id) conflict.mark();
    formError.value = errorMessage(err, uiText("保存失败"));
    notifyError(err, uiText("保存失败"));
    return false;
  } finally {
    saving.value = false;
  }
}
async function publish() {
  const epoch = context;
  if (conflict.active.value || saving.value || !canPublish.value || editing.value?.status !== "draft")
    return;
  if ((!editing.value.id || guard.dirty.value) && !(await save())) return;
  if (!editing.value?.id || !currentSession(epoch)) return;
  saving.value = true;
  try {
    const response = await onlineFormsApi.publish(
      editing.value.id,
      editing.value.version,
    );
    if (!currentSession(epoch)) return;
    loadEditor(response.data.data || response.data);
    await load();
    ElMessage.success(uiText("已发布"));
  } catch (err) {
    if (!currentSession(epoch)) return;
    if (responseStatus(err) === 409 && editing.value?.id) conflict.mark();
    formError.value = errorMessage(err, uiText("发布失败"));
    notifyError(err, uiText("发布失败"));
  } finally {
    saving.value = false;
  }
}
async function checkDefinition() {
  const epoch = context;
  if (!editing.value || saving.value || !canValidate.value) return;
  saving.value = true;
  formError.value = "";
  try {
    await onlineFormsApi.validate(editing.value.definition);
    if (currentSession(epoch)) feedback.value = uiText("表单定义校验通过");
  } catch (err) {
    if (currentSession(epoch))
      formError.value = errorMessage(err, uiText("校验失败"));
  } finally {
    saving.value = false;
  }
}
async function validatePreview() {
  const epoch = context;
  if (!editing.value || saving.value || !canValidate.value) return;
  saving.value = true;
  previewErrors.value = {};
  previewSuccess.value = false;
  formError.value = "";
  try {
    const data = submissionValues(editing.value.definition.fields, previewValues.value);
    const hasAttachments = editing.value.definition.fields.some(field => ['file', 'relation'].includes(field.type) || field.fields?.some(child => ['file', 'relation'].includes(child.type)));
    if (editing.value.id && hasAttachments) await onlineFormAttachmentsApi.validatePreview(editing.value.id, editing.value.definition, data);
    else await onlineFormsApi.validate(editing.value.definition, data);
    if (currentSession(epoch)) previewSuccess.value = true;
  } catch (err) {
    if (currentSession(epoch)) {
      previewErrors.value = fieldErrors(err);
      formError.value = errorMessage(err, uiText("校验失败"));
    }
  } finally {
    saving.value = false;
  }
}
async function importDefinition() {
  const epoch = context;
  if (locked.value) return;
  saving.value = true;
  importError.value = "";
  try {
    const raw = JSON.parse(importText.value) as OnlineFormDefinition;
    const response = await onlineFormsApi.validate(raw);
    if (!currentSession(epoch) || !editing.value) return;
    editing.value.definition = upgrade(response.data.data.definition);
    resetPreview();
    importOpen.value = false;
    importText.value = "";
  } catch (err) {
    if (!currentSession(epoch)) return;
    importError.value = errorMessage(
      err,
      uiText("导入失败，请检查 JSON 与字段规则"),
    );
  } finally {
    saving.value = false;
  }
}
async function exportDefinition() {
  const epoch = context;
  if (!editing.value || saving.value || !canValidate.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const response = await onlineFormsApi.validate(editing.value.definition);
    if (!currentSession(epoch)) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(response.data.data.definition, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${editing.value.code || "online-form"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    if (!currentSession(epoch)) return;
    formError.value = errorMessage(err, uiText("导出失败"));
  } finally {
    saving.value = false;
  }
}
watch(() => tenants.currentId, () => {
  context++;
  beginRead();
  forms.value = []; total.value = 0; page.value = 1;
  guard.discard(); error.value = ''; formError.value = ''; feedback.value = '';
  previewErrors.value = {}; previewSuccess.value = false;
  void load();
}, { flush: 'sync' });
onMounted(load);
</script>
<style scoped>
.page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.head h2 {
  font-size: 16px;
  margin: 0;
}
.head p,
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.actions :deep(button) {
  margin-left: 0;
}
.editor-actions {
  margin-bottom: 12px;
}
.identity {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.section-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 8px;
  margin: 10px 0;
}
h3 {
  font-size: 15px;
  margin: 20px 0 12px;
}
.failure {
  color: var(--el-color-danger);
  overflow-wrap: anywhere;
}
.feedback {
  color: var(--el-color-success);
}
.runtime-link {
  margin-top: 18px;
}
.page :deep(.el-pagination) {
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}
@media (max-width: 768px) {
  .head {
    flex-direction: column;
    align-items: flex-start;
  }
  .identity {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
  .section-row {
    grid-template-columns: minmax(0, 1fr);
  }
  .actions {
    width: 100%;
  }
  .actions :deep(button) {
    flex: 1;
    min-height: 44px;
  }
  .section-row button {
    min-height: 44px;
  }
}
</style>
