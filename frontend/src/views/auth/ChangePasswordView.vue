<template>
  <main class="password-page">
    <BaseCard class="password-card">
      <h1>{{ uiText('设置个人密码') }}</h1>
      <p>{{ uiText('当前密码由管理员设置，请先修改密码再使用系统') }}</p>
      <ChangePasswordForm />
      <el-button class="sign-out" :loading="leaving" @click="leave">{{ uiText('退出登录') }}</el-button>
    </BaseCard>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { BaseCard } from '@/components'
import ChangePasswordForm from '@/components/auth/ChangePasswordForm.vue'
import { uiText } from '@/i18n/uiText'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const leaving = ref(false)
async function leave() {
  if (leaving.value) return
  leaving.value = true
  try { await auth.logout() } catch { /* 本地会话已清理，允许重新登录。 */ }
  finally { leaving.value = false; await router.replace('/login') }
}
</script>

<style scoped>
.password-page { min-height: 100dvh; display: grid; place-items: center; padding: var(--spacing-lg); background: var(--color-bg-page); }
.password-card { width: 100%; max-width: 460px; }
h1 { font-size: var(--font-size-xl); margin: 0 0 var(--spacing-md); }
p { color: var(--color-text-secondary); margin: 0 0 var(--spacing-xl); line-height: 1.6; }
.sign-out { margin-top: var(--spacing-lg); }
</style>
