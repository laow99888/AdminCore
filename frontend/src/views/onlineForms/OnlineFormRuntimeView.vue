<template>
  <AppLayout
    ><div class="runtime-page">
      <BaseCard v-if="form"
        ><template #header
          ><h2>{{ form.name }}</h2></template
        >
        <OnlineFormRenderer
          v-model="values"
          :definition="form.definition"
          :errors="errors"
          :disabled="saving"
        />
        <p v-if="error" role="alert" class="error">{{ error }}</p>
        <p v-if="success" role="status">{{ uiText("提交成功") }}</p>
        <BaseButton variant="primary" :disabled="saving" @click="submit">{{
          saving ? uiText("提交中") : uiText("提交")
        }}</BaseButton> </BaseCard
      ><BaseCard v-else
        ><p v-if="loading" role="status">{{ uiText("表单加载中") }}</p>
        <el-empty
          v-else
          :description="error || uiText('表单加载失败')"
        /><el-button v-if="!loading" @click="load">{{
          uiText("重试")
        }}</el-button></BaseCard
      >
    </div></AppLayout
  >
</template>
<script setup lang="ts">
import "@/components/onlineForms/messages";
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import AppLayout from "@/components/layout/AppLayout.vue";
import { BaseButton, BaseCard } from "@/components";
import { onlineFormsApi, type OnlineFormRow } from "@/api";
import { errorMessage } from "@/api/request";
import { uiText } from "@/i18n/uiText";
import { useUnsavedChanges } from "@/composables/useUnsavedChanges";
import OnlineFormRenderer from "@/components/onlineForms/OnlineFormRenderer.vue";
import {
  activeValues,
  fieldErrors,
  initialValues,
  type FormValues,
} from "@/components/onlineForms/runtime";
const route = useRoute(),
  form = ref<OnlineFormRow>(),
  values = ref<FormValues>({}),
  errors = ref<Record<string, string>>({}),
  error = ref(""),
  success = ref(false),
  saving = ref(false),
  loading = ref(false);
let read = 0,
  pending: { body: string; key: string } | undefined;
const guard = useUnsavedChanges({
  source: () => values.value,
  busy: () => saving.value,
  clear: () => {
    read++;
    form.value = undefined;
    values.value = {};
    errors.value = {};
    pending = undefined;
  },
});
watch(
  values,
  () => {
    success.value = false;
    errors.value = {};
  },
  { deep: true, flush: "sync" },
);
async function load() {
  const current = ++read;
  form.value = undefined;
  values.value = {};
  error.value = "";
  loading.value = true;
  pending = undefined;
  try {
    const response = await onlineFormsApi.published(String(route.params.code));
    if (current !== read || !guard.isSessionCurrent()) return;
    form.value = response.data.data;
    values.value = initialValues(form.value.definition.fields);
    guard.markClean();
  } catch (err) {
    if (current === read && guard.isSessionCurrent())
      error.value = errorMessage(err, uiText("表单加载失败"));
  } finally {
    if (current === read) loading.value = false;
  }
}
async function submit() {
  if (!form.value || saving.value) return;
  saving.value = true;
  error.value = "";
  errors.value = {};
  success.value = false;
  const data =
    form.value.definition.schema_version === 2
      ? activeValues(form.value.definition.fields, values.value)
      : values.value;
  const body = JSON.stringify(data);
  if (!pending || pending.body !== body)
    pending = { body, key: `online-form-${crypto.randomUUID()}` };
  try {
    await onlineFormsApi.createRecord(form.value.code, data, pending.key);
    if (!guard.isSessionCurrent()) return;
    values.value = initialValues(form.value.definition.fields);
    pending = undefined;
    guard.markClean();
    success.value = true;
  } catch (err) {
    if (guard.isSessionCurrent()) {
      errors.value = fieldErrors(err);
      error.value = errorMessage(err, uiText("提交失败，请检查字段"));
    }
  } finally {
    saving.value = false;
  }
}
watch(() => route.params.code, load, { immediate: true });
</script>
<style scoped>
.runtime-page {
  min-width: 0;
  max-width: 1100px;
  margin: auto;
}
.runtime-page h2 {
  font-size: 18px;
  margin: 0;
}
.error {
  color: var(--el-color-danger);
  overflow-wrap: anywhere;
}
</style>
