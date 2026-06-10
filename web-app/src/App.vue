<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'

const route = useRoute()

/** Pages that render full-screen without sidebar/topbar */
const isFullPage = computed(() => {
  const name = route.name as string
  return !name || ['login', 'register', 'landing', 'profile-setup'].includes(name)
})
</script>

<template>
  <AppLayout v-if="!isFullPage">
    <router-view />
  </AppLayout>
  <router-view v-else />
</template>
