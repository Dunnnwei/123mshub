<script setup>
import { ref } from 'vue'
import { AlertTriangle, Check, Inbox, Sparkles, Trash2, X } from '@lucide/vue'
import { api } from '../api'
import TagInput from './TagInput.vue'

defineProps({
  items: { type: Array, default: () => [] },
  tagSuggestions: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh', 'toast', 'admitted', 'request-discard-all'])

const expandedFile = ref('')
const busyFile = ref('')
const aiBusyFile = ref('')
const forms = ref({})
const errors = ref({})

const typeOptions = [
  { value: 'user', label: 'user · 用户' },
  { value: 'project', label: 'project · 项目' },
  { value: 'reference', label: 'reference · 参考' },
  { value: 'feedback', label: 'feedback · 反馈' },
]

function formOf(item) {
  if (!forms.value[item.file]) {
    forms.value[item.file] = {
      title: item.title || '',
      name: item.suggested_name || '',
      description: item.description || '',
      type: item.type || 'reference',
      tags: [...(item.tags || [])],
    }
  }
  return forms.value[item.file]
}

function toggle(item) {
  expandedFile.value = expandedFile.value === item.file ? '' : item.file
}

async function aiComplete(item) {
  aiBusyFile.value = item.file
  try {
    const result = await api.memoryAiDraft(item.body)
    const form = formOf(item)
    // 与编辑抽屉一致：只补空位，不覆盖用户已填的标题/描述
    if (result.title && !form.title.trim()) form.title = result.title
    if (result.description && !form.description.trim()) form.description = result.description
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    aiBusyFile.value = ''
  }
}

async function admit(item) {
  const form = formOf(item)
  busyFile.value = item.file
  errors.value = { ...errors.value, [item.file]: '' }
  try {
    const entry = await api.admitMemoryInbox(item.file, {
      title: form.title,
      name: form.name,
      description: form.description,
      type: form.type,
      tags: form.tags,
    })
    emit('admitted', entry)
    emit('toast', { type: 'success', message: `记忆「${entry.title}」已收编入库。` })
    emit('refresh')
  } catch (error) {
    errors.value = { ...errors.value, [item.file]: error.message }
  } finally {
    busyFile.value = ''
  }
}

async function discard(item) {
  busyFile.value = item.file
  try {
    await api.discardMemoryInbox(item.file)
    emit('toast', { type: 'success', message: `已丢弃投递 ${item.file}。` })
    emit('refresh')
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    busyFile.value = ''
  }
}
</script>

<template>
  <div class="inbox-view">
    <header class="view-heading inbox-heading">
      <div>
        <h1>待收编投递</h1>
        <p>agent 按注入提示词投递到 inbox 的记忆，审核后收编入库；可疑内容会有红条警告。</p>
      </div>
      <button
        v-if="items.length > 1"
        class="danger-button"
        type="button"
        @click="emit('request-discard-all')"
      ><Trash2 :size="15" /> 全部丢弃</button>
    </header>

    <p v-if="loading" class="inbox-empty">
      <Inbox :size="18" /> 正在读取投递列表…
    </p>

    <p v-else-if="!items.length" class="inbox-empty">
      <Inbox :size="18" /> 没有待收编的投递。把注入提示词发给你的 agent，它投递的记忆会出现在这里。
    </p>

    <article v-for="item in items" :key="item.file" class="inbox-card" :class="{ expanded: expandedFile === item.file }">
      <button class="inbox-card-head" type="button" @click="toggle(item)">
        <span class="inbox-card-title">{{ item.title || formOf(item).title || item.file }}</span>
        <span class="inbox-card-meta">
          <span v-if="!item.has_frontmatter" class="inbox-flag">无 frontmatter</span>
          <span v-if="item.injection_hits.length" class="inbox-flag danger">
            <AlertTriangle :size="12" /> 疑似注入 {{ item.injection_hits.length }} 处
          </span>
          <span class="inbox-file">{{ item.file }}</span>
        </span>
      </button>

      <div v-if="expandedFile === item.file" class="inbox-card-body">
        <div v-if="item.injection_hits.length" class="inbox-injection-warning" role="alert">
          <AlertTriangle :size="15" />
          <div>
            <strong>检测到疑似提示词注入内容，请仔细审阅。</strong>
            <ul>
              <li v-for="(hit, index) in item.injection_hits.slice(0, 4)" :key="index">
                第 {{ hit.line }} 行 · {{ hit.rule }}：<code>{{ hit.excerpt }}</code>
              </li>
            </ul>
          </div>
        </div>

        <div class="inbox-split">
          <div class="inbox-raw">
            <span class="inbox-split-label">投递原文（只读）</span>
            <pre>{{ item.raw_text }}</pre>
          </div>
          <div class="inbox-form">
            <span class="inbox-split-label">收编表单（可编辑）</span>
            <div class="field-block">
              <label>标题 <b class="required-mark">*</b></label>
              <input v-model="formOf(item).title" type="text" placeholder="中文标题" maxlength="60" />
            </div>
            <div class="field-block">
              <label>条目名</label>
              <input v-model="formOf(item).name" type="text" spellcheck="false" maxlength="64" />
            </div>
            <div class="field-block">
              <label>类型</label>
              <select v-model="formOf(item).type">
                <option v-for="option in typeOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div class="field-block">
              <label>标签</label>
              <TagInput v-model="formOf(item).tags" :suggestions="tagSuggestions" />
            </div>
            <div class="field-block">
              <label>一句话描述</label>
              <input v-model="formOf(item).description" type="text" maxlength="120" />
            </div>
            <small v-if="errors[item.file]" class="field-error" role="alert">{{ errors[item.file] }}</small>
            <div class="inbox-form-actions">
              <button
                class="secondary-button"
                type="button"
                :disabled="aiBusyFile === item.file"
                @click="aiComplete(item)"
              ><Sparkles :size="14" /> {{ aiBusyFile === item.file ? '生成中…' : 'AI 补全标题与描述' }}</button>
            </div>
          </div>
        </div>

        <footer class="inbox-card-actions">
          <button
            class="danger-button"
            type="button"
            :disabled="busyFile === item.file"
            @click="discard(item)"
          ><X :size="14" /> 丢弃</button>
          <button
            class="primary-button"
            type="button"
            :disabled="busyFile === item.file || !formOf(item).title.trim()"
            @click="admit(item)"
          ><Check :size="14" /> {{ busyFile === item.file ? '处理中…' : '收编入库' }}</button>
        </footer>
      </div>
    </article>
  </div>
</template>
