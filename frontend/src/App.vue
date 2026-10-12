<template>
  <el-config-provider :locale="elementLocale">
    <div class="app-container">
      <router-view :key="locale" />
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">

import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { useThemeStore } from './stores/theme'

const themeStore = useThemeStore()
const { locale } = useI18n()
const elementLocale = computed(() => locale.value === 'en-US' ? en : zhCn)

onMounted(() => {
  themeStore.initTheme()
})
</script>

<style scoped>
.app-container {
  width: 100%;
  min-height: 100vh;
}
</style>
