<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Bot, Brain, ClipboardCopy, FileText, Inbox, Plus, RefreshCw, Search, Sparkles, X,
} from '@lucide/vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import MemoryDrawer from './MemoryDrawer.vue'
import MemoryInbox from './MemoryInbox.vue'

const props = defineProps({
  enabled: { type: Boolean, default: true },
})
const emit = defineEmits(['toast', 'copy-prompt', 'stats', 'confirm'])

const loading = ref(true)
const subview = ref('list') // 'list' | 'inbox'
const entries = ref([])
const allNames = ref([]) // 未过滤的全量条目名（重名校验用，不随筛选缩水）
const stats = ref({ total: 0, types: {}, this_week: 0, inbox_pending: 0, index_warn: false })
const typeFilter = ref('all')
const search = ref('')
const sort = ref('updated')
const searchTimer = ref(null)
let requestSeq = 0 // 竞态保护：只接受最新一次列表请求的响应
const inboxItems = ref([])
const inboxLoading = ref(false)

const drawerOpen = ref(false)
const drawerMode = ref('edit')
const drawerEntry = ref(null)
const indexOpen = ref(false)
const indexContent = ref('')
const indexNote = ref('')
const rebuilding = ref(false)

// ---- 整理与日报 ----
const tidyBusy = ref(false)
const reportsOpen = ref(false)
const reportList = ref([])
const activeReport = ref(null) // {file, content}
const dutyOpen = ref(false)

const typeTabs = computed(() => [
  { value: 'all', label: '全部', count: stats.value.total },
  { value: 'user', label: 'user · 用户', count: stats.value.types.user || 0 },
  { value: 'project', label: 'project · 项目', count: stats.value.types.project || 0 },
  { value: 'reference', label: 'reference · 参考', count: stats.value.types.reference || 0 },
  { value: 'feedback', label: 'feedback · 反馈', count: stats.value.types.feedback || 0 },
])

const tagSuggestions = computed(() => {
  const catalog = new Map()
  entries.value.forEach((entry) => {
    ;(entry.tags || []).forEach((tag) => {
      const key = String(tag).toLocaleLowerCase()
      if (!catalog.has(key)) catalog.set(key, tag)
    })
  })
  return [...catalog.values()]
})

const existingNames = computed(() => allNames.value)

onMounted(() => {
  refreshAll()
})

onUnmounted(() => {
  if (searchTimer.value) window.clearTimeout(searchTimer.value)
})

watch(search, () => {
  if (searchTimer.value) window.clearTimeout(searchTimer.value)
  searchTimer.value = window.setTimeout(refreshEntries, 300)
})
watch([typeFilter, sort], () => {
  // 防抖合并：快速切换筛选/排序时只发最后一次
  if (searchTimer.value) window.clearTimeout(searchTimer.value)
  searchTimer.value = window.setTimeout(refreshEntries, 120)
})

async function refreshAll() {
  if (!props.enabled) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    await Promise.all([refreshEntries(), refreshStats()])
  } finally {
    loading.value = false
  }
}

async function refreshEntries() {
  if (!props.enabled) return
  const seq = ++requestSeq
  try {
    const result = await api.memoryEntries({
      type: typeFilter.value === 'all' ? '' : typeFilter.value,
      q: search.value.trim(),
      sort: sort.value,
    })
    if (seq !== requestSeq) return // 已有更新的请求，丢弃过期响应
    entries.value = result.items
    if (!search.value.trim() && typeFilter.value === 'all') {
      allNames.value = result.items.map((entry) => entry.name)
    } else if (result.items.length < stats.value.total) {
      allNames.value = await loadAllNames()
    }
    if (result.inbox_pending !== undefined) {
      stats.value = { ...stats.value, inbox_pending: result.inbox_pending }
      emit('stats', stats.value)
    }
  } catch (error) {
    if (seq === requestSeq) emit('toast', { type: 'error', message: error.message })
  }
}

async function loadAllNames() {
  try {
    const result = await api.memoryEntries({ sort: 'name' })
    return result.items.map((entry) => entry.name)
  } catch {
    return allNames.value
  }
}

async function refreshStats() {
  if (!props.enabled) return
  try {
    const result = await api.memoryStats()
    stats.value = result
    emit('stats', result)
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function openInbox() {
  subview.value = 'inbox'
  inboxLoading.value = true
  try {
    const result = await api.memoryInbox()
    inboxItems.value = result.items
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    inboxLoading.value = false
  }
}

async function inboxRefreshed() {
  await Promise.all([openInbox(), refreshStats()])
  await refreshEntries()
}

function inboxAdmitted() {
  // 收编后回列表并刷新统计（openInbox 会重拉收编列表）
}

function openCreate() {
  drawerMode.value = 'create'
  drawerEntry.value = null
  drawerOpen.value = true
}

async function openEntry(item) {
  try {
    drawerMode.value = 'edit'
    drawerEntry.value = await api.memoryEntry(item.name)
    drawerOpen.value = true
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function openEntryByName(name) {
  await openEntry({ name })
}

async function drawerSaved() {
  await refreshAll()
}

async function drawerRemoved() {
  drawerOpen.value = false
  await refreshAll()
}

function requestDelete(entry) {
  emit('confirm', {
    title: `删除记忆「${entry.title}」？`,
    message: '条目文件会移入 .meta\\memory-trash 留档（软删除），索引会立即重建。',
    confirmLabel: '删除记忆',
    tone: 'danger',
    action: () => performDelete(entry),
  })
}

async function performDelete(entry) {
  try {
    await api.deleteMemoryEntry(entry.name)
    emit('toast', { type: 'success', message: `记忆「${entry.title}」已删除（软删除，可在 .meta/memory-trash 找回）。` })
    await refreshAll()
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

function requestDiscardAll() {
  emit('confirm', {
    title: `丢弃全部 ${stats.value.inbox_pending} 条投递？`,
    message: '待收编的投递会全部移入回收站。此操作不可批量撤销，请确认里面没有你还想要的内容。',
    confirmLabel: '全部丢弃',
    tone: 'danger',
    action: performDiscardAll,
  })
}

async function performDiscardAll() {
  try {
    const result = await api.discardAllMemoryInbox()
    emit('toast', { type: 'success', message: `已丢弃 ${result.discarded} 条投递。` })
    await inboxRefreshed()
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function openIndexFile() {
  try {
    const result = await api.memoryIndexFile()
    indexContent.value = result.content || '（索引文件尚未生成）'
    indexNote.value = result.note || ''
    indexOpen.value = true
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function rebuildNow() {
  rebuilding.value = true
  try {
    const result = await api.memoryRebuild()
    emit('toast', {
      type: 'success',
      message: `记忆对账完成：共 ${result.total_count} 条${result.index_rewritten ? '，索引已重建' : '，索引无变化'}。`,
    })
    await refreshAll()
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    rebuilding.value = false
  }
}

async function runTidy() {
  tidyBusy.value = true
  try {
    const result = await api.memoryTidy(true)
    if (result.ai_error) {
      emit('toast', { type: 'warning', message: `整理完成，但 AI 分析未生成：${result.ai_error}` })
    } else if (result.has_ai) {
      emit('toast', { type: 'success', message: '归纳整理完成，日报已生成（含 AI 分析）。' })
    } else {
      emit('toast', { type: 'success', message: '归纳整理完成，日报已生成。' })
    }
    activeReport.value = { file: result.file, content: result.content }
    reportList.value = (await api.memoryReports()).items
    reportsOpen.value = true
    await refreshAll()
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  } finally {
    tidyBusy.value = false
  }
}

async function openReports() {
  try {
    reportList.value = (await api.memoryReports()).items
    if (!activeReport.value && reportList.value.length) {
      await openReport(reportList.value[0].file)
    }
    reportsOpen.value = true
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function openReport(file) {
  try {
    const result = await api.memoryReport(file)
    activeReport.value = { file: result.file, content: result.content }
  } catch (error) {
    emit('toast', { type: 'error', message: error.message })
  }
}

async function copyDutyPrompt() {
  try {
    const result = await api.memoryDutyPrompt()
    await navigator.clipboard.writeText(result.prompt)
    emit('toast', { type: 'success', message: '值守整理提示词已复制，粘贴给你的值守 agent（如 NAS 总机）即可部署。' })
  } catch (error) {
    emit('toast', { type: 'error', message: `复制失败：${error.message}` })
  }
}

defineExpose({
  refreshAll,
})

const typeClass = (type) => `memory-type-${type}`
</script>

<template>
  <section class="memory-view">
    <header class="view-heading memory-heading">
      <div>
        <h1>记忆库</h1>
        <p>一人一条知识的共享记忆：索引 + 条目文件，注入提示词让 agent 读它、投递它。</p>
      </div>
      <button class="primary-button" type="button" @click="emit('copy-prompt')">
        <ClipboardCopy :size="16" /> 复制注入提示词
      </button>
    </header>

    <div v-if="!enabled" class="empty-state">
      <div class="empty-symbol"><Brain :size="26" /></div>
      <h2>先完成仓库配置</h2>
      <p>记忆库住在共享仓库里。到「设置」设定仓库位置后，这里就能新建记忆、收编投递、整理日报。</p>
    </div>

    <template v-else>
    <div class="memory-stats-bar" role="region" aria-label="记忆统计">
      <button
        type="button"
        class="memory-stat"
        :class="{ active: typeFilter === 'all' }"
        @click="typeFilter = 'all'"
      ><Brain :size="15" /><span>总记忆</span><b>{{ stats.total }}</b></button>
      <button
        v-for="tab in typeTabs.slice(1)"
        :key="tab.value"
        type="button"
        class="memory-stat"
        :class="{ active: typeFilter === tab.value }"
        @click="typeFilter = tab.value"
      ><span>{{ tab.label }}</span><b>{{ tab.count }}</b></button>
      <span class="memory-stat muted"><span>本周新增</span><b>{{ stats.this_week }}</b></span>
      <button
        type="button"
        class="memory-stat inbox"
        :class="{ active: subview === 'inbox' }"
        @click="subview === 'inbox' ? (subview = 'list') : openInbox()"
      ><Inbox :size="15" /><span>待收编</span><b>{{ stats.inbox_pending }}</b></button>
      <span class="memory-stat-actions">
        <button type="button" class="inline-link" @click="openIndexFile">
          <FileText :size="13" /> 查看索引源文件
        </button>
        <button
          type="button"
          class="inline-link"
          :disabled="rebuilding"
          title="对账 notes 目录并重建 MEMORY.md 索引"
          @click="rebuildNow"
        ><RefreshCw :size="13" :class="{ spin: rebuilding }" /> 重建索引</button>
      </span>
    </div>

    <p v-if="stats.index_warn" class="memory-index-warn" role="alert">
      索引规模已超过 150 行 / 20KB（当前 {{ stats.index_lines }} 行）。部分 agent 只加载索引前 200 行，
      超出条目可能读不到——建议清理或合并低价值记忆。
    </p>

    <MemoryInbox
      v-if="subview === 'inbox'"
      :items="inboxItems"
      :tag-suggestions="tagSuggestions"
      :loading="inboxLoading"
      @refresh="inboxRefreshed"
      @toast="(payload) => emit('toast', payload)"
      @admitted="inboxAdmitted"
      @request-discard-all="requestDiscardAll"
    />

    <template v-else>
      <div class="toolbar">
        <label class="search-field">
          <Search :size="17" />
          <input
            v-model="search"
            placeholder="搜索标题、描述、标签或正文"
            aria-label="搜索记忆"
          />
          <button v-if="search" type="button" aria-label="清除搜索" @click="search = ''"><X :size="15" /></button>
        </label>
        <label class="filter-select">
          <span>排序</span>
          <select v-model="sort">
            <option value="updated">最近更新</option>
            <option value="created">创建时间</option>
            <option value="name">名称</option>
          </select>
        </label>
        <button
          class="secondary-button"
          type="button"
          :disabled="tidyBusy"
          title="盘点记忆与技能并生成整理日报（配置了 AI 接口时附 AI 分析）"
          @click="runTidy"
        ><Sparkles :size="16" :class="{ spin: tidyBusy }" /> {{ tidyBusy ? '整理中…' : '归纳整理' }}</button>
        <button class="secondary-button" type="button" @click="openReports">
          <FileText :size="16" /> 整理日报
        </button>
        <button
          class="secondary-button"
          type="button"
          title="把值守整理提示词交给一个 agent（如 NAS 总机），由它周期整理并写日报"
          @click="dutyOpen = true"
        ><Bot :size="16" /> 值守 Agent</button>
        <button class="secondary-button" type="button" @click="openInbox" v-if="stats.inbox_pending">
          <Inbox :size="16" /> 收编投递（{{ stats.inbox_pending }}）
        </button>
        <button class="primary-button" type="button" @click="openCreate">
          <Plus :size="16" /> 新建记忆
        </button>
      </div>

      <div v-if="loading && !entries.length" class="memory-loading">正在读取记忆库…</div>

      <div v-else-if="entries.length" class="memory-list">
        <article
          v-for="entry in entries"
          :key="entry.name"
          class="memory-row"
          role="button"
          tabindex="0"
          @click="openEntry(entry)"
          @keydown.enter="openEntry(entry)"
        >
          <div class="memory-row-main">
            <strong class="memory-row-title">{{ entry.title }}</strong>
            <span class="memory-row-desc">{{ entry.description || '（没有描述）' }}</span>
          </div>
          <div class="memory-row-meta">
            <span class="memory-badge" :class="typeClass(entry.type)">{{ entry.type }}</span>
            <span class="memory-badge source" :class="{ agent: entry.source === 'agent' }">
              {{ entry.source_label }}
            </span>
            <span v-for="tag in entry.tags.slice(0, 4)" :key="tag" class="memory-tag">#{{ tag }}</span>
            <span class="memory-row-date" :title="`创建 ${entry.created || '—'}`">
              更新 {{ entry.updated || '—' }}
            </span>
          </div>
        </article>
      </div>

      <div v-else class="empty-state">
        <div class="empty-symbol"><Brain :size="26" /></div>
        <h2>{{ search || typeFilter !== 'all' ? '没有匹配的记忆' : '记忆库还是空的' }}</h2>
        <p v-if="search || typeFilter !== 'all'">换个关键词或切回「全部」试试。</p>
        <p v-else>新建一条记忆，或复制注入提示词发给你的 agent，让它开始投递。</p>
        <div v-if="!search && typeFilter === 'all'" class="empty-actions">
          <button class="primary-button" type="button" @click="openCreate"><Plus :size="15" /> 新建一条记忆</button>
          <button class="secondary-button" type="button" @click="emit('copy-prompt')">
            <ClipboardCopy :size="15" /> 复制注入提示词
          </button>
        </div>
      </div>
    </template>
    </template>

    <MemoryDrawer
      :open="drawerOpen"
      :mode="drawerMode"
      :entry="drawerEntry"
      :existing-names="existingNames"
      :tag-suggestions="tagSuggestions"
      @close="drawerOpen = false"
      @saved="drawerSaved"
      @created="drawerSaved"
      @remove="requestDelete"
      @toast="(payload) => emit('toast', payload)"
      @open-entry="openEntryByName"
    />

    <div v-if="indexOpen" class="drawer-backdrop" @click.self="indexOpen = false">
      <section class="detail-drawer memory-index-drawer" role="dialog" aria-label="索引源文件">
        <header class="drawer-header">
          <div class="drawer-title">
            <span>索引源文件</span>
            <h2>MEMORY.md（只读）</h2>
          </div>
          <button class="icon-button" type="button" aria-label="关闭" @click="indexOpen = false">
            <X :size="18" />
          </button>
        </header>
        <div class="drawer-content">
          <p class="memory-index-note">{{ indexNote }}</p>
          <pre class="memory-index-pre">{{ indexContent }}</pre>
        </div>
      </section>
    </div>

    <div v-if="reportsOpen" class="drawer-backdrop" @click.self="reportsOpen = false">
      <section class="detail-drawer memory-report-drawer" role="dialog" aria-label="整理日报">
        <header class="drawer-header">
          <div class="drawer-title">
            <span>整理日报</span>
            <h2>{{ activeReport ? activeReport.file : '暂无日报' }}</h2>
          </div>
          <button class="icon-button" type="button" aria-label="关闭" @click="reportsOpen = false">
            <X :size="18" />
          </button>
        </header>
        <div class="drawer-content memory-report-body">
          <aside v-if="reportList.length" class="memory-report-list">
            <button
              v-for="report in reportList"
              :key="report.file"
              type="button"
              :class="{ active: activeReport?.file === report.file }"
              @click="openReport(report.file)"
            >{{ report.file }}</button>
            <p v-if="!reportList.length">还没有日报，点「归纳整理」生成第一份。</p>
          </aside>
          <div v-if="activeReport" class="memory-report-content md-preview" v-html="renderMarkdown(activeReport.content)"></div>
          <p v-else class="memory-index-note">还没有日报。点工具栏的「归纳整理」立即生成一份，或部署值守 Agent 让它周期整理。</p>
        </div>
      </section>
    </div>

    <div v-if="dutyOpen" class="drawer-backdrop" @click.self="dutyOpen = false">
      <section class="detail-drawer memory-duty-drawer" role="dialog" aria-label="值守 Agent">
        <header class="drawer-header">
          <div class="drawer-title">
            <span>值守 Agent</span>
            <h2>把整理收纳交给一个 agent</h2>
          </div>
          <button class="icon-button" type="button" aria-label="关闭" @click="dutyOpen = false">
            <X :size="18" />
          </button>
        </header>
        <div class="drawer-content">
          <p>
            复制「值守整理提示词」，粘贴给一个常驻 agent（例如 NAS 上的总机、定时任务的本地 agent）。
            它会周期性整理记忆（合并重复、补描述、修双链）并按模板把日报写进记忆库的
            <code>reports\</code> 目录——之后在这里的「整理日报」里随时可看。
          </p>
          <p class="memory-duty-note">
            不想部署 agent？直接用工具栏的「归纳整理」手动跑一次：程序本地盘点，
            配置了「AI 接口」（设置里的安全检查同一条线路）时还会附上 LLM 的整理分析。
          </p>
          <ul class="memory-duty-list">
            <li>值守 agent 有值守权限：可直接编辑 notes\ 条目（普通接入的 agent 只能投递 inbox）。</li>
            <li>日报内容仅限记忆与技能的汇报信息，不含其他。</li>
            <li>两条路可以并存：agent 值守日常，手动「归纳整理」随时补一份。</li>
          </ul>
        </div>
        <footer class="drawer-actions">
          <span class="drawer-actions-spacer"></span>
          <button class="primary-button" type="button" @click="copyDutyPrompt">
            <ClipboardCopy :size="15" /> 复制值守整理提示词
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
