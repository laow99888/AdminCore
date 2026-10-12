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
            <div class="profile">
              <div class="avatar">
                <UserRound :size="30" :stroke-width="1.5" />
              </div>
              <div class="profile-info">
                <div class="username">{{ authStore.user?.username || '—' }}</div>
                <div class="email">{{ authStore.user?.email || '' }}</div>
              </div>
            </div>
          </BaseCard>
        </el-col>

        <!-- 修改密码 -->
        <el-col :xs="24" :lg="14">
          <BaseCard>
            <template #header>
              <div class="card-header-title">{{ uiText("修改密码") }}</div>
            </template>
            <el-form :model="pwdForm" label-width="90px" class="pwd-form">
              <el-form-item :label="uiText('当前密码')" required>
                <el-input v-model="pwdForm.old" type="password" show-password />
              </el-form-item>
              <el-form-item :label="uiText('新密码')" required>
                <el-input v-model="pwdForm.new1" type="password" show-password :placeholder="uiText('至少 8 位')" />
              </el-form-item>
              <el-form-item :label="uiText('确认新密码')" required>
                <el-input v-model="pwdForm.new2" type="password" show-password />
              </el-form-item>
              <el-form-item>
                <BaseButton variant="primary" :loading="saving" @click="handleChangePassword">{{ uiText("保存修改") }}</BaseButton>
              </el-form-item>
            </el-form>
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
          </BaseCard>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { UserRound } from 'lucide-vue-next'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton } from '@/components'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import authApi from '@/api/auth'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const { locale } = useI18n()
const saving = ref(false)

const currentLocale = ref(locale.value)

const pwdForm = reactive({
  old: '',
  new1: '',
  new2: '',
})

const switchLanguage = (value: string) => {
  locale.value = value
  currentLocale.value = value
  localStorage.setItem('language', value)
}

const handleChangePassword = async () => {
  if (!pwdForm.old || !pwdForm.new1) {
    ElMessage.warning(uiText("请填写当前密码和新密码"))
    return
  }
  if (pwdForm.new1 !== pwdForm.new2) {
    ElMessage.warning(uiText("两次输入的新密码不一致"))
    return
  }
  if (pwdForm.new1.length < 8) {
    ElMessage.warning(uiText("新密码至少 8 位"))
    return
  }
  saving.value = true
  try {
    await authApi.changePassword(pwdForm.old, pwdForm.new1, pwdForm.new2)
    ElMessage.success(uiText("密码修改成功，请使用新密码重新登录"))
    authStore.clearSession()
    window.location.href = '/login'
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
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

.profile {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-md) 0;
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-bg-elevated);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
}

.username {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.email {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: var(--spacing-xs);
}

.pwd-form {
  max-width: 420px;
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
