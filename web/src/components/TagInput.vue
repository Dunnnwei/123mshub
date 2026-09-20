<script setup>
import { computed, ref } from 'vue'
import { Plus, X } from '@lucide/vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  suggestions: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const input = ref('')
const error = ref('')
const maxTags = 12
const maxLength = 24

const availableSuggestions = computed(() => {
  const selected = new Set(props.modelValue.map((tag) => tag.toLocaleLowerCase()))
  return props.suggestions
    .filter((tag) => !selected.has(String(tag).toLocaleLowerCase()))
    .slice(0, 8)
})

function commit(raw = input.value) {
  error.value = ''
  const additions = String(raw)
    .split(/[,，]/)
    .map((tag) => tag.trim().replace(/^#/, '').trim().replace(/\s+/g, ' '))
    .filter(Boolean)
  if (!additions.length) {
    input.value = ''
    return
  }
  const next = [...props.modelValue]
  const seen = new Set(next.map((tag) => String(tag).toLocaleLowerCase()))
  for (const tag of additions) {
    if (tag.length > maxLength) {
      error.value = `单个标签不能超过 ${maxLength} 个字符`
      continue
    }
    const key = tag.toLocaleLowerCase()
    if (seen.has(key)) continue
    if (next.length >= maxTags) {
      error.value = `每个技能最多设置 ${maxTags} 个标签`
      break
    }
    seen.add(key)
    next.push(tag)
  }
  emit('update:modelValue', next)
  input.value = ''
}

function remove(index) {
  emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
  error.value = ''
}

function onKeydown(event) {
  if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
    event.preventDefault()
    commit()
  } else if (event.key === 'Backspace' && !input.value && props.modelValue.length) {
    remove(props.modelValue.length - 1)
  }
}
</script>

<template>
  <div class="tag-input-block">
    <div class="tag-input-shell" :class="{ disabled }" @click="$refs.tagField?.focus()">
      <span v-for="(tag, index) in modelValue" :key="`${tag}-${index}`" class="tag-token">
        <span>#{{ tag }}</span>
        <button
          type="button"
          :aria-label="`移除标签 ${tag}`"
          :disabled="disabled"
          @mousedown.prevent
          @click.stop="remove(index)"
        >
          <X :size="12" />
        </button>
      </span>
      <input
        ref="tagField"
        v-model="input"
        :disabled="disabled || modelValue.length >= maxTags"
        :maxlength="maxLength"
        :placeholder="modelValue.length ? '继续添加' : '输入标签后按 Enter'"
        aria-label="输入技能标签"
        @keydown="onKeydown"
        @blur="commit()"
      />
      <button
        v-if="input.trim()"
        class="tag-add-button"
        type="button"
        aria-label="添加当前标签"
        :disabled="disabled"
        @mousedown.prevent
        @click="commit()"
      >
        <Plus :size="14" />
      </button>
    </div>
    <div v-if="availableSuggestions.length" class="tag-suggestions">
      <span>已有标签</span>
      <button
        v-for="tag in availableSuggestions"
        :key="tag"
        type="button"
        :disabled="disabled"
        @mousedown.prevent
        @click="commit(tag)"
      >
        #{{ tag }}
      </button>
    </div>
    <small v-if="error" class="tag-input-error" role="alert">{{ error }}</small>
    <small v-else class="tag-input-help">Enter 或逗号确认；最多 12 个，每个不超过 24 个字符。</small>
  </div>
</template>
