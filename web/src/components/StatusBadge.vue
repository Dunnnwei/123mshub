<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'unchecked' },
  compact: { type: Boolean, default: false },
})

const label = computed(() => ({
  safe: '安全无风险',
  warning: '需要确认',
  error: '检查失败',
  unchecked: '尚未检查',
})[props.status] || props.status)
</script>

<template>
  <span class="status-badge" :class="[`status-${status}`, { compact }]">
    <span class="status-dot" aria-hidden="true"></span>
    {{ label }}
  </span>
</template>

