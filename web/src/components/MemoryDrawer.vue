<script setup>
import { computed, ref, watch } from 'vue'
import { Eye, Maximize2, Minimize2, Pencil, Save, Sparkles, Trash2, X } from '@lucide/vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import TagInput from './TagInput.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'edit' }, // 'create' | 'edit'
  entry: { type: Object, default: null },
  existingNames: { type: Array, default: () => [] },
  tagSuggestions: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved', 'created', 'remove', 'toast', 'open-entry'])

const title = ref('')
const name = ref('')
const description = ref('')
const type = ref('reference')
const tags = ref([])
const body = ref('')
const created = ref('')
const updated = ref('')
const links = ref([])
const previewMode = ref(false)
const expanded = ref(false)
const busy = ref('')
const conflict = ref('')
const conflictName = ref('')
const error = ref('')

const typeOptions = [
  { value: 'user', label: 'user · 用户' },
  { value: 'project', label: 'project · 项目' },
  { value: 'reference', label: 'reference · 参考' },
  { value: 'feedback', label: 'feedback · 反馈' },
]

watch(
  () => [props.open, props.entry, props.mode],
  ([open]) => {
    if (!open) return
    conflict.value = ''
    conflictName.value = ''
    error.value = ''
    previewMode.value = false
    expanded.value = false
    busy.value = ''
    const entry = props.entry || {}
    title.value = entry.title || ''
    name.value = props.mode === 'create' ? '' : (entry.name || '')
    description.value = entry.description || ''
    type.value = entry.type || 'reference'
    tags.value = [...(entry.tags || [])]
    body.value = entry.body || ''
    created.value = entry.created || ''
    updated.value = entry.updated || ''
    links.value = entry.links || []
  },
)

function sanitizeSlug(value) {
  return String(value || '')
    .trim().toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}

// 纯中文标题提不出 ASCII 词：与后端 slug_from_title 同规则生成兜底名
//（sha256 前 4 位，跨会话稳定）
function fallbackSlug(sourceTitle) {
  const stamp = `${String(new Date().getMonth() + 1).padStart(2, '0')}${String(new Date().getDate()).padStart(2, '0')}`
  let hash1 = 0x811c9dc5
  let hash2 = 0x01000193
  for (const ch of String(sourceTitle)) {
    const code = ch.codePointAt(0)
    hash1 = (hash1 ^ code) >>> 0
    hash1 = (hash1 * 0x01000193) >>> 0
    hash2 = (hash2 + code * 31) >>> 0
  }
  const digest = (hash1.toString(16) + hash2.toString(16)).slice(0, 4).padStart(4, '0')
  return sanitizeSlug(`note-${stamp}-${digest}`)
}

const namePreview = computed(() => {
  const slug = sanitizeSlug(name.value || title.value)
  if (slug || !String(title.value || '').trim()) return slug
  return fallbackSlug(title.value)
})
const nameInvalid = computed(() => Boolean((name.value || title.value) && !namePreview.value))
const nameConflict = computed(() => {
  const candidate = namePreview.value
  if (!candidate) return false
  if (props.mode === 'edit' && candidate === props.entry?.name) return false
  return props.existingNames.includes(candidate)
})

const canSave = computed(() => (
  title.value.trim() && namePreview.value && !nameInvalid.value && !nameConflict.value && !busy.value
))

const previewHtml = computed(() => renderMarkdown(body.value))

async function save() {
  if (!canSave.value) return
  busy.value = 'save'
  conflict.value = ''
  error.value = ''
  const payload = {
    title: title.value.trim(),
    name: namePreview.value,
    description: description.value.trim(),
    type: type.value,
    tags: tags.value,
    body: body.value,
  }
  try {
    const result = props.mode === 'create'
      ? await api.createMemoryEntry(payload)
      : await api.updateMemoryEntry(props.entry.name, payload)
    emit(props.mode === 'create' ? 'created' : 'saved', result)
    emit('toast', { type: 'success', message: `记忆「${result.title}」已保存。` })
    emit('close')
  } catch (err) {
    if (String(err.message || '').includes('已有同名条目')) {
      conflict.value = err.message
      conflictName.value = namePreview.value
    } else {
      error.value = err.message
    }
  } finally {
    busy.value = ''
  }
}

async function aiDraft() {
  if (!body.value.trim()) {
    emit('toast', { type: 'warning', message: '先写点正文，AI 才能拟标题与描述。' })
    return
  }
  busy.value = 'ai'
  try {
    const result = await api.memoryAiDraft(body.value)
    if (result.description) description.value = result.description
    if (result.title && !title.value.trim()) title.value = result.title
    emit('toast', { type: 'success', message: 'AI 已生成草稿，确认后再保存。' })
  } catch (err) {
    emit('toast', { type: 'error', message: err.message })
  } finally {
    busy.value = ''
  }
}

function requestRemove() {
  emit('remove', props.entry)
}
</script>

<template>
  <div v-if="open" class="drawer-backdrop memory-drawer-layer" @click.self="emit('close')">
    <section
      class="detail-drawer memory-drawer"
      :class="{ 'memory-drawer-expanded': expanded }"
      role="dialog"
      aria-label="记忆条目编辑"
    >
      <header class="drawer-header">
        <div class="drawer-title">
          <span>{{ mode === 'create' ? '新建记忆' : '编辑记忆' }}</span>
          <h2>{{ title || '未命名记忆' }}</h2>
        </div>
        <button
          class="icon-button"
          type="button"
          :aria-label="expanded ? '还原编辑窗口' : '放大编辑窗口'"
          :title="expanded ? '还原编辑窗口' : '放大编辑窗口'"
          @click="expanded = !expanded"
        >
          <Minimize2 v-if="expanded" :size="18" />
          <Maximize2 v-else :size="18" />
        </button>
        <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="18" />
        </button>
      </header>

      <div class="drawer-content memory-drawer-content">
        <div class="field-block">
          <label for="memory-title">标题 <b class="required-mark">*</b></label>
          <input id="memory-title" v-model="title" type="text" placeholder="中文标题（必填）" maxlength="60" />
        </div>

        <div class="field-block">
          <label for="memory-name">条目名（kebab-case，即文件名）</label>
          <input
            id="memory-name"
            v-model="name"
            type="text"
            :placeholder="mode === 'create' ? '留空则从标题自动生成' : ''"
            maxlength="64"
            spellcheck="false"
          />
          <small v-if="namePreview" class="field-help">
            净化后的条目名：<code>{{ namePreview }}</code>
          </small>
          <small v-if="nameInvalid" class="field-error" role="alert">
            条目名净化后为空：只能用英文小写字母、数字和短横线（纯中文标题会自动生成兜底名）。
          </small>
          <small v-if="nameConflict" class="field-error" role="alert">
            已有同名条目。
            <button type="button" class="inline-link" @click="emit('open-entry', namePreview)">打开它</button>
          </small>
          <small v-if="conflict" class="field-error" role="alert">{{ conflict }}</small>
        </div>

        <div class="field-row">
          <div class="field-block">
            <label for="memory-type">类型</label>
            <select id="memory-type" v-model="type">
              <option v-for="option in typeOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <div class="field-block memory-dates" v-if="mode === 'edit'">
            <span class="field-readonly">创建：{{ created || '—' }}</span>
            <span class="field-readonly">更新：{{ updated || '—' }}（保存时自动刷新）</span>
          </div>
        </div>

        <div class="field-block">
          <label>标签</label>
          <TagInput v-model="tags" :suggestions="tagSuggestions" />
        </div>

        <div class="field-block">
          <label for="memory-description">一句话描述</label>
          <input
            id="memory-description"
            v-model="description"
            type="text"
            placeholder="索引行展示的一句话（可点下方 AI 按钮生成）"
            maxlength="120"
          />
        </div>

        <div class="field-block memory-editor-block">
          <div class="memory-editor-head">
            <label for="memory-body">正文</label>
            <div class="segment-toggle" role="group" aria-label="编辑或预览">
              <button
                type="button"
                :class="{ active: !previewMode }"
                @click="previewMode = false"
              ><Pencil :size="13" /> 编辑</button>
              <button
                type="button"
                :class="{ active: previewMode }"
                @click="previewMode = true"
              ><Eye :size="13" /> 预览</button>
            </div>
          </div>
          <textarea
            v-if="!previewMode"
            id="memory-body"
            v-model="body"
            class="memory-body-editor"
            rows="12"
            spellcheck="false"
            placeholder="事实 + 为什么 + 怎么用。一个文件只写一条知识；可用 [[条目名]] 双链引用其他记忆。"
          ></textarea>
          <div v-else class="memory-body-preview md-preview" v-html="previewHtml"></div>
        </div>

        <div v-if="mode === 'edit' && links.length" class="field-block">
          <label>相关记忆（双链）</label>
          <div class="memory-link-row">
            <button
              v-for="link in links"
              :key="link.name"
              type="button"
              class="memory-link-token"
              :class="{ missing: !link.exists }"
              :disabled="!link.exists"
              :title="link.exists ? '打开这条记忆' : '指向的条目未创建'"
              @click="link.exists && emit('open-entry', link.name)"
            >
              [[{{ link.name }}]]<em v-if="!link.exists">未创建</em>
            </button>
          </div>
        </div>

        <small v-if="error" class="field-error" role="alert">{{ error }}</small>
      </div>

      <footer class="drawer-actions">
        <button
          v-if="mode === 'edit'"
          class="danger-button"
          type="button"
          @click="requestRemove"
        ><Trash2 :size="15" /> 删除</button>
        <span class="drawer-actions-spacer"></span>
        <button
          class="secondary-button"
          type="button"
          :disabled="busy === 'ai'"
          title="调用设置里的 AI 接口，从正文生成一句话描述（标题为空时一并生成）"
          @click="aiDraft"
        ><Sparkles :size="15" /> {{ busy === 'ai' ? '生成中…' : (mode === 'create' ? 'AI 补全标题与描述' : 'AI 生成描述') }}</button>
        <button
          class="primary-button"
          type="button"
          :disabled="!canSave || busy === 'save'"
          @click="save"
        ><Save :size="15" /> {{ busy === 'save' ? '保存中…' : '保存' }}</button>
      </footer>
    </section>
  </div>
</template>
