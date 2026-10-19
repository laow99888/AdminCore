<!-- 仅供文档类型检查的内存示例，未注册路由，也未被应用入口引用；无 API 请求。 -->
<template>
  <BaseCard title="基础组件示例（本地内存）">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <BaseTable
      :data="pageRows" :columns="columns" :loading="loading" :total="rows.length"
      :current-page="page" :page-size="pageSize" :show-actions="false" show-toolbar row-key="id"
      @update:currentPage="page = $event" @update:pageSize="changePageSize"
    >
      <template #toolbar>
        <BaseButton variant="primary" :disabled="loading" @click="openEditor">新增演示记录</BaseButton>
      </template>
    </BaseTable>
    <BaseDialog v-model="open" title="新增演示记录" width="560px" :loading="saving" :before-close="confirmClose">
      <BaseForm v-if="open" v-model="draft" :fields="fields" :rules="rules" :loading="saving" @submit="save" />
      <!-- BaseForm 自带提交和重置；替换 footer 避免出现第二组确认按钮。 -->
      <template #footer><BaseButton :disabled="saving" @click="closeEditor">关闭</BaseButton></template>
    </BaseDialog>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElAlert, ElMessageBox } from 'element-plus'
import BaseButton from '@/components/common/BaseButton.vue'
import BaseCard from '@/components/common/BaseCard.vue'
import BaseTable from '@/components/common/BaseTable.vue'
import BaseForm from '@/components/common/BaseForm.vue'
import BaseDialog from '@/components/common/BaseDialog.vue'

const rows = ref([{ id: 1, name: '示例记录' }])
const columns = [{ prop: 'name', label: '名称' }]
const fields = [{ prop: 'name', label: '名称', type: 'text' as const, required: true }]
const rules = { name: [{ required: true, message: '请填写名称', trigger: 'blur' }] }
const draft = ref({ name: '' }), page = ref(1), pageSize = ref(10)
const loading = ref(false), saving = ref(false), open = ref(false), error = ref('')
const pageRows = computed(() => rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

function changePageSize(value: number) { pageSize.value = value; page.value = 1 }
function openEditor() { draft.value = { name: '' }; error.value = ''; open.value = true }
async function confirmClose() {
  if (saving.value) return false
  if (!draft.value.name) return true
  return ElMessageBox.confirm('放弃此演示草稿吗？', '提示').then(() => true, () => false)
}
async function closeEditor() { if (await confirmClose()) open.value = false }
function save(value: Record<string, unknown>) {
  if (saving.value || typeof value.name !== 'string') return
  rows.value.push({ id: rows.value.length + 1, name: value.name })
  draft.value = { name: '' }; open.value = false
}
</script>
