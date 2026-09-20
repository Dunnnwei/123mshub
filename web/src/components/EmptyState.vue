<script setup>
import { PackagePlus } from '@lucide/vue'

defineProps({
  filtered: { type: Boolean, default: false },
})
defineEmits(['add', 'clear'])
</script>

<template>
  <div class="empty-state">
    <div class="empty-symbol"><PackagePlus :size="26" /></div>
    <h2>{{ filtered ? '没有匹配的技能或项目' : '从第一个技能或项目开始' }}</h2>
    <p v-if="filtered">换一个关键词或清除筛选条件。</p>
    <p v-else>输入 GitHub 地址，既可收录 Agent 技能，也可完整克隆并持续更新应用项目。</p>
    <button v-if="filtered" class="secondary-button" type="button" @click="$emit('clear')">清除筛选</button>
    <button v-else class="primary-button" type="button" @click="$emit('add')">添加技能或项目</button>
  </div>
</template>
