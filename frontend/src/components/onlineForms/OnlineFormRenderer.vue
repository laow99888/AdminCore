<template>
  <el-form label-position="top" :disabled="disabled" @submit.prevent>
    <OnlineFormFields
      :fields="definition.fields"
      :section="definition.sections?.length ? '' : undefined"
      :model-value="modelValue"
      :errors="errors"
      :disabled="disabled"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <section
      v-for="section in definition.sections"
      :key="section.key"
      class="section"
    >
      <h3>{{ section.title }}</h3>
      <OnlineFormFields
        :fields="definition.fields"
        :section="section.key"
        :model-value="modelValue"
        :errors="errors"
        :disabled="disabled"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </section>
  </el-form>
</template>
<script setup lang="ts">
import type { OnlineFormDefinition } from "@/api";
import type { FormValues } from "./runtime";
import OnlineFormFields from "./OnlineFormFields.vue";
defineProps<{
  definition: OnlineFormDefinition;
  modelValue: FormValues;
  errors?: Record<string, string>;
  disabled?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: FormValues] }>();
</script>
<style scoped>
.section h3 {
  font-size: 15px;
  border-bottom: 1px solid var(--el-border-color);
  padding-bottom: 12px;
  margin: 16px 0;
}
</style>
