<template>
  <span class="private-avatar" role="img" :aria-label="uiText('个人头像')" :aria-busy="auth.avatarLoading">
    <img v-if="auth.avatarUrl" :src="auth.avatarUrl" alt="" @error="auth.avatarDecodeFailed" />
    <UserRound v-else :size="iconSize" :stroke-width="1.5" aria-hidden="true" />
  </span>
</template>

<script setup lang="ts">
import { UserRound } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'
withDefaults(defineProps<{ iconSize?: number }>(), { iconSize: 24 })
const auth = useAuthStore()
</script>

<style scoped>
.private-avatar { width: 100%; height: 100%; display: inline-flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 50%; }
img { width: 100%; height: 100%; object-fit: cover; }
</style>
