<script setup>
import { AlertTriangle, LoaderCircle, X } from '@lucide/vue'

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: '确认' },
  tone: { type: String, default: 'normal' },
  busy: { type: Boolean, default: false },
})
defineEmits(['close', 'confirm'])
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop confirm-backdrop" @mousedown.self="$emit('close')">
        <section class="modal-panel confirm-modal" role="alertdialog" aria-modal="true">
          <header class="modal-header">
            <div class="confirm-heading">
              <span class="confirm-icon" :class="{ danger: tone === 'danger' }"><AlertTriangle :size="20" /></span>
              <h2>{{ title }}</h2>
            </div>
            <button class="icon-button" type="button" aria-label="关闭" :disabled="busy" @click="$emit('close')">
              <X :size="19" />
            </button>
          </header>
          <div class="modal-body">
            <p class="confirm-message">{{ message }}</p>
          </div>
          <footer class="modal-footer">
            <button class="secondary-button" type="button" :disabled="busy" @click="$emit('close')">取消</button>
            <button :class="tone === 'danger' ? 'danger-confirm-button' : 'primary-button'" type="button" :disabled="busy" @click="$emit('confirm')">
              <LoaderCircle v-if="busy" class="spinning" :size="17" />
              {{ busy ? '正在处理…' : confirmLabel }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
