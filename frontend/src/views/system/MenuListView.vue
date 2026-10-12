<template>
  <AppLayout>
    <div class="menu-list-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("菜单结构（只读，由后端权限系统下发）") }}</div>
            <BaseButton variant="ghost" @click="loadMenus">{{ uiText("刷新") }}</BaseButton>
          </div>
        </template>

        <el-table
          v-loading="loading"
          :data="menuTree"
          row-key="id"
          default-expand-all
          style="width: 100%"
        >
          <el-table-column prop="name" :label="uiText('菜单名')" min-width="180" />
          <el-table-column prop="path" :label="uiText('路由路径')" min-width="160" />
          <el-table-column :label="uiText('图标')" width="80">
            <template #default="{ row }">
              <component
                :is="iconComponents[row.icon]"
                v-if="iconComponents[row.icon]"
                :size="16"
                :stroke-width="1.75"
                aria-hidden="true"
              />
              <span v-else>{{ row.icon || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="order" :label="uiText('排序')" width="80" />
          <el-table-column :label="uiText('可见')" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_visible ? 'success' : 'info'" size="small">
                {{ row.is_visible ? uiText("可见") : uiText("隐藏") }}
              </el-tag>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="uiText('暂无菜单数据（数据库中尚未初始化菜单）')" :image-size="80" />
          </template>
        </el-table>
      </BaseCard>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref } from 'vue'
import {
  LayoutDashboard, Users, ShieldCheck, ListTree, FolderOpen,
  ClipboardCheck, Bell, ListChecks, FileText, Settings,
} from 'lucide-vue-next'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton } from '@/components'
import { menusApi, type MenuRow } from '@/api'

// 与后端 bootstrap_admincore 种子的 icon 名对应（AppSidebar 同款图标）
const iconComponents: Record<string, unknown> = {
  'layout-dashboard': LayoutDashboard,
  users: Users,
  'shield-check': ShieldCheck,
  'list-tree': ListTree,
  'folder-open': FolderOpen,
  'clipboard-check': ClipboardCheck,
  bell: Bell,
  'list-checks': ListChecks,
  'file-text': FileText,
  settings: Settings,
}

const loading = ref(false)
const menuTree = ref<MenuRow[]>([])

const loadMenus = async () => {
  loading.value = true
  try {
    menuTree.value = await menusApi.list()
  } finally {
    loading.value = false
  }
}

loadMenus()
</script>

<style scoped>
.menu-list-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}
</style>
