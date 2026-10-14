<template>
  <AppLayout>
    <div class="settings-container">
      <el-row :gutter="16">
        <!-- 个人信息 -->
        <el-col :xs="24" :lg="10">
          <BaseCard>
            <template #header>
              <div class="card-header-title">{{ uiText("个人信息") }}</div>
            </template>
            <ProfileEditor />
          </BaseCard>
        </el-col>

        <!-- 修改密码 -->
        <el-col :xs="24" :lg="14">
          <BaseCard>
            <template #header>
              <div class="card-header-title">{{ uiText("修改密码") }}</div>
            </template>
            <ChangePasswordForm />
          </BaseCard>
        </el-col>

        <!-- 外观 -->
        <el-col :span="24">
          <BaseCard>
            <template #header>
              <div class="card-header-title">{{ uiText("外观与语言") }}</div>
            </template>
            <el-row :gutter="24">
              <el-col :xs="24" :sm="12">
                <div class="setting-row">
                  <div>
                    <div class="setting-label">{{ uiText("深色模式") }}</div>
                    <div class="setting-desc">{{ uiText("切换明暗主题") }}</div>
                  </div>
                  <el-switch :model-value="themeStore.isDark" @change="themeStore.toggleTheme()" />
                </div>
              </el-col>
              <el-col :xs="24" :sm="12">
                <div class="setting-row">
                  <div>
                    <div class="setting-label">{{ uiText("界面语言") }}</div>
                    <div class="setting-desc">{{ uiText("界面显示语言") }}</div>
                  </div>
                  <el-select :model-value="currentLocale" style="width: 120px" @change="switchLanguage">
                    <el-option :label="uiText('中文')" value="zh-CN" />
                    <el-option label="English" value="en-US" />
                  </el-select>
                </div>
              </el-col>
            </el-row>
            <TableDensitySettings />
            <WatermarkSettings />
          </BaseCard>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import ChangePasswordForm from '@/components/auth/ChangePasswordForm.vue'
import ProfileEditor from '@/components/auth/ProfileEditor.vue'
import TableDensitySettings from '@/components/settings/TableDensitySettings.vue'
import WatermarkSettings from '@/components/settings/WatermarkSettings.vue'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const { locale } = useI18n()

const currentLocale = computed(() => locale.value)

const switchLanguage = (value: string) => {
  locale.value = value
  localStorage.setItem('language', value)
}

onMounted(() => {
  if (!authStore.user) authStore.fetchUser()
})
</script>

<style scoped>
.settings-container {
  width: 100%;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) 0;
}

.setting-label {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.setting-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 2px;
}
</style>
