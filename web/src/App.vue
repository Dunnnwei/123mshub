<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Archive, ArrowDownCircle, BookOpenText, Brain, CheckSquare, ChevronDown, CircleHelp, ClipboardCopy, FolderOpen, Languages, ListCheck, Menu,
  Moon, PackagePlus, RefreshCw, Search, Settings, ShieldCheck, Sun, Tags, X,
} from '@lucide/vue'
import { api } from './api'
import { startJobPolling, stopJobPolling, wakeJobPolling, jobStore } from './jobStore'
import logoUrl from './assets/123mshublogo.svg'
import logoHeiUrl from './assets/123mshublogohei.svg'
import AddSkillModal from './components/AddSkillModal.vue'
import ConfirmModal from './components/ConfirmModal.vue'
import DetailDrawer from './components/DetailDrawer.vue'
import EmptyState from './components/EmptyState.vue'
import MemoryView from './components/MemoryView.vue'
import MemoryGraph from './components/MemoryGraph.vue'
import ScanModal from './components/ScanModal.vue'
import SecurityView from './components/SecurityView.vue'
import SettingsView from './components/SettingsView.vue'
import SkillRow from './components/SkillRow.vue'
import TaskPanel from './components/TaskPanel.vue'

const loading = ref(true)
const fatalError = ref('')
const health = ref({ configured: false, skill_count: 0 })
const config = ref({})
const skills = ref([])
const view = ref('library')
const memoryStats = ref({ total: 0, inbox_pending: 0 })
const search = ref('')
const statusFilter = ref('all')
const selectedTag = ref('__all__')
const selectedSkill = ref(null)
const detailOpen = ref(false)
const detailLoading = ref(false)
const addOpen = ref(false)
const scanOpen = ref(false)
const scanSkill = ref(null)
const mobileNavOpen = ref(false)
const busyAction = ref('')
const busySkillName = ref('')
const toast = ref(null)
const toastTimer = ref(null)
let reconcileTimer = null
const scanInitialReport = ref(null)
const selectionMode = ref(false)
const selectedNames = ref([])
const batchScanOpen = ref(false)
const batchScanRoute = ref('offline')
const sourceFilter = ref('all')
const assetFilter = ref('all')
const tagsExpanded = ref(localStorage.getItem('mshub-tags-expanded') === '1')
const selectionBox = ref(null)
let selectionOrigin = null
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
const effectiveLocale = computed(() => {
  if (config.value.language === 'en' || config.value.language === 'zh-CN') return config.value.language
  return navigator.language?.toLocaleLowerCase().startsWith('en') ? 'en' : 'zh-CN'
})

watch(effectiveLocale, (locale) => {
  document.documentElement.lang = locale
  document.documentElement.dataset.locale = locale
}, { immediate: true })

function syncThemeMeta() {
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme.value === 'dark' ? '#030711' : '#F7F5F2')
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('theme', theme.value)
  syncThemeMeta()
}

function skillKey(skill) {
  return `${skill.name}|${skill.library || ''}`
}

const selectedSkills = computed(() => (
  selectedNames.value
    .map((key) => skills.value.find((item) => skillKey(item) === key))
    .filter(Boolean)
))
const selectedWarningCount = computed(() => selectedSkills.value.filter((item) => item.security_status === 'warning').length)
const confirmState = ref({
  open: false,
  title: '',
  message: '',
  confirmLabel: '',
  tone: 'normal',
  action: null,
})

const filteredSkills = computed(() => {
  const term = search.value.trim().toLowerCase()
  return skills.value.filter((skill) => {
    const matchesTerm = !term || [skill.name, skill.description, skill.description_zh, skill.author, ...(skill.tags || [])]
      .some((value) => String(value || '').toLowerCase().includes(term))
    const matchesStatus = statusFilter.value === 'all' || skill.security_status === statusFilter.value
    const matchesSource = sourceFilter.value === 'all'
      || (sourceFilter.value === 'local' && skill.provider === 'local')
      || (sourceFilter.value === 'github' && skill.provider !== 'local')
      || (sourceFilter.value.startsWith('from:') && (skill.imported_from || '') === sourceFilter.value.slice(5))
    const matchesAsset = assetFilter.value === 'all'
      || (assetFilter.value === 'project' && skill.item_type === 'project')
      || (assetFilter.value === 'skill' && skill.item_type !== 'project')
    const matchesTag = selectedTag.value === '__all__'
      || (selectedTag.value === '__untagged__' && !(skill.tags || []).length)
      || (
        selectedTag.value.startsWith('tag:')
        && (skill.tags || []).some(
          (tag) => tag.toLocaleLowerCase() === selectedTag.value.slice(4),
        )
      )
    return matchesTerm && matchesStatus && matchesTag && matchesSource && matchesAsset
  })
})

const tagOptions = computed(() => {
  const catalog = new Map()
  skills.value.forEach((skill) => {
    const itemTags = skill.tags || []
    itemTags.forEach((tag) => {
      const key = String(tag).toLocaleLowerCase()
      const current = catalog.get(key) || { key, name: tag, count: 0 }
      current.count += 1
      catalog.set(key, current)
    })
  })
  return [...catalog.values()].sort((a, b) => (
    b.count - a.count || String(a.name).localeCompare(String(b.name), 'zh-CN')
  ))
})
const tagSuggestions = computed(() => tagOptions.value.map((item) => item.name))
const untaggedCount = computed(() => skills.value.filter((item) => !(item.tags || []).length).length)
const filterActive = computed(() => (
  search.value.trim() || statusFilter.value !== 'all' || selectedTag.value !== '__all__' || sourceFilter.value !== 'all' || assetFilter.value !== 'all'
))
const safeCount = computed(() => skills.value.filter((item) => item.security_status === 'safe').length)
const warningCount = computed(() => skills.value.filter((item) => item.security_status === 'warning').length)

onMounted(() => {
  syncThemeMeta()
  loadApp()
  startJobPolling(jobFinished)
})

onUnmounted(() => {
  stopJobPolling()
  if (reconcileTimer) window.clearTimeout(reconcileTimer)
})

async function loadApp() {
  loading.value = true
  fatalError.value = ''
  try {
    const [healthData, configData] = await Promise.all([api.health(), api.config()])
    health.value = healthData
    config.value = { ...configData, ai_presets: [] }
    // 预设不属于启动关键路径，失败只降级为空列表，不拖垮主界面
    try {
      const presetData = await api.aiPresets()
      config.value = { ...config.value, ai_presets: presetData.items }
    } catch (presetError) {
      console.warn('AI 预设加载失败', presetError)
    }
    if (healthData.configured) {
      await refreshSkills()
      // 首屏就要有记忆待收编红点：导航徽章不等用户进记忆页才刷新
      try {
        memoryStats.value = await api.memoryStats()
      } catch (memoryError) {
        console.warn('记忆统计加载失败', memoryError)
      }
    } else {
      view.value = 'settings'
    }
    if (healthData.reconcile_pending) scheduleReconcileRefresh()
  } catch (error) {
    fatalError.value = error.message
  } finally {
    loading.value = false
  }
}

function scheduleReconcileRefresh(attempt = 0) {
  if (reconcileTimer) window.clearTimeout(reconcileTimer)
  if (attempt >= 20) return
  reconcileTimer = window.setTimeout(async () => {
    try {
      const next = await api.health()
      health.value = { ...health.value, ...next }
      if (!next.reconcile_pending) {
        await refreshSkills()
        try { memoryStats.value = await api.memoryStats() } catch { /* optional badge refresh */ }
        return
      }
    } catch {
      // A transient background check failure should not interrupt the usable UI.
    }
    scheduleReconcileRefresh(attempt + 1)
  }, attempt === 0 ? 420 : 650)
}

async function refreshSkills(selectName = '') {
  const result = await api.listSkills()
  skills.value = result.items
  health.value.skill_count = skills.value.length
  if (selectName || selectedSkill.value) {
    const key = selectName || skillKey(selectedSkill.value)
    selectedSkill.value = skills.value.find((item) => skillKey(item) === key)
      || skills.value.find((item) => item.name === key.split('|')[0])
      || null
    if (!selectedSkill.value) detailOpen.value = false
  }
}

function navigate(target) {
  view.value = target
  mobileNavOpen.value = false
}

function clearFilters() {
  search.value = ''
  statusFilter.value = 'all'
  selectedTag.value = '__all__'
  sourceFilter.value = 'all'
  assetFilter.value = 'all'
}

function showToast(payload) {
  if (toastTimer.value) window.clearTimeout(toastTimer.value)
  toast.value = typeof payload === 'string' ? { type: 'success', message: payload } : payload
  toastTimer.value = window.setTimeout(() => { toast.value = null }, 4800)
}

async function selectSkill(skill) {
  // 先打开抽屉再取详情：慢磁盘或同步盘不会让用户误以为点击失效。
  selectedSkill.value = skill
  detailLoading.value = true
  detailOpen.value = true
  try {
    selectedSkill.value = await api.skill(skill.name, skill.library)
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  } finally {
    detailLoading.value = false
  }
}

async function copyPrompt(skill) {
  try {
    const result = await api.prompt(skill.name, skill.library)
    await navigator.clipboard.writeText(result.prompt)
    showToast({ type: 'success', message: `${skill.name} 的${skill.item_type === 'project' ? '项目使用提示' : '技能使用提示词'}已复制。` })
  } catch (error) {
    showToast({ type: 'error', message: `复制失败：${error.message}` })
  }
}

async function copyInjectionPrompt() {
  try {
    const result = await api.libraryPrompt()
    await navigator.clipboard.writeText(result.prompt)
    showToast({ type: 'success', message: '注入提示词已复制，粘贴到任意 Agent（对话首条消息或常驻配置）即可接入记忆库与技能库。' })
  } catch (error) {
    showToast({ type: 'error', message: `复制失败：${error.message}` })
  }
}

async function runAction(skill, action, handler) {
  busyAction.value = action
  busySkillName.value = skill.name
  try {
    return await handler()
  } catch (error) {
    showToast({ type: 'error', message: error.message })
    return null
  } finally {
    busyAction.value = ''
    busySkillName.value = ''
  }
}

async function checkVersion(skill) {
  const result = await runAction(skill, 'check', () => api.checkVersion(skill.name, skill.library))
  if (!result) return
  showToast({
    type: result.has_update ? 'warning' : 'success',
    message: result.has_update
      ? `发现新版本 ${result.remote_hash.slice(0, 12)}，可以更新。`
      : `${skill.name} 已是最新版本。`,
  })
}

async function updateSkill(skill) {
  try {
    await api.startUpdate(skill.name, skill.library)
    wakeJobPolling()
    showToast({ type: 'success', message: `${skill.name} 已转入后台更新，可在右下角任务面板查看进度。` })
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  }
}

function requestTrust(skill) {
  confirmState.value = {
    open: true,
    title: `信任 ${skill.name}？`,
    message: '确认你信任此技能来源（作者/仓库/用途）。信任后安全状态转为“安全无风险”，检查记录会被人工放行标记覆盖，后续更新不再因此项拦截。',
    confirmLabel: '确认信任',
    tone: 'normal',
    action: () => performTrust(skill),
  }
}

async function performTrust(skill) {
  const result = await runAction(skill, 'trust', () => api.trust(skill.name, skill.library))
  if (!result) return
  confirmState.value.open = false
  await refreshSkills(skillKey(skill))
  if (detailOpen.value) await selectSkill({ name: skill.name, library: skill.library })
  if (scanOpen.value) scanClosed()
  showToast({ type: 'success', message: `${skill.name} 已标记为信任来源。` })
}

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) selectedNames.value = []
}

function toggleSelected(skill) {
  const key = skillKey(skill)
  selectedNames.value = selectedNames.value.includes(key)
    ? selectedNames.value.filter((item) => item !== key)
    : [...selectedNames.value, key]
}

function selectAllFiltered() {
  const keys = filteredSkills.value.map((item) => skillKey(item))
  const allSelected = keys.length > 0 && keys.every((key) => selectedNames.value.includes(key))
  selectedNames.value = allSelected
    ? selectedNames.value.filter((key) => !keys.includes(key))
    : [...new Set([...selectedNames.value, ...keys])]
}

async function batchScan() {
  const targets = [...selectedSkills.value]
  if (!targets.length) return
  batchScanOpen.value = true
}

async function runBatchScan() {
  const targets = [...selectedSkills.value]
  batchScanOpen.value = false
  const failed = []
  let queued = 0
  for (const item of targets) {
    try {
      await api.startScan({ name: item.name, library: item.library, route: batchScanRoute.value })
      queued += 1
    } catch (error) {
      failed.push(`${item.name}：${error.message}`)
    }
  }
  if (queued) wakeJobPolling()
  if (failed.length) {
    showToast({ type: 'error', message: `已排队 ${queued} 项，失败 ${failed.length} 项（${failed[0]}）。` })
  } else {
    showToast({ type: 'success', message: `${queued} 个条目已排队安全检查，进度见任务面板。` })
  }
}

function toggleTagsExpanded() {
  tagsExpanded.value = !tagsExpanded.value
  localStorage.setItem('mshub-tags-expanded', tagsExpanded.value ? '1' : '0')
}

function selectionStart(event) {
  if (!selectionMode.value || event.button !== 0 || event.target.closest('button,input')) return
  const list = event.currentTarget.getBoundingClientRect()
  selectionOrigin = { x: event.clientX, y: event.clientY, left: list.left, top: list.top }
  selectionBox.value = { left: event.clientX - list.left, top: event.clientY - list.top, width: 0, height: 0 }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}
function selectionMove(event) {
  if (!selectionOrigin) return
  const list = event.currentTarget.getBoundingClientRect()
  const left = Math.min(selectionOrigin.x, event.clientX) - list.left
  const top = Math.min(selectionOrigin.y, event.clientY) - list.top
  selectionBox.value = { left, top, width: Math.abs(event.clientX - selectionOrigin.x), height: Math.abs(event.clientY - selectionOrigin.y) }
  const box = { left: Math.min(selectionOrigin.x, event.clientX), right: Math.max(selectionOrigin.x, event.clientX), top: Math.min(selectionOrigin.y, event.clientY), bottom: Math.max(selectionOrigin.y, event.clientY) }
  const hits = [...event.currentTarget.querySelectorAll('.skill-row[data-skill-key]')].filter((row) => {
    const rect = row.getBoundingClientRect()
    return rect.right >= box.left && rect.left <= box.right && rect.bottom >= box.top && rect.top <= box.bottom
  }).map((row) => row.dataset.skillKey)
  if (selectionBox.value.width > 8 || selectionBox.value.height > 8) selectedNames.value = [...new Set([...selectedNames.value, ...hits])]
}
function selectionEnd() { selectionOrigin = null; selectionBox.value = null }

async function batchUpdate() {
  if (!selectedNames.value.length) return
  const updatable = selectedSkills.value.filter((item) => item.provider !== 'local')
  if (!updatable.length) {
    showToast({ type: 'warning', message: '所选条目都是本地自研技能，没有可在线更新的项。' })
    return
  }
  const failed = []
  let queued = 0
  for (const item of updatable) {
    try {
      await api.startUpdate(item.name, item.library)
      queued += 1
    } catch (error) {
      failed.push(`${item.name}：${error.message}`)
    }
  }
  if (queued) wakeJobPolling()
  if (failed.length) {
    showToast({ type: 'error', message: `已排队 ${queued} 项，失败 ${failed.length} 项（${failed[0]}）。` })
  } else {
    showToast({ type: 'success', message: `${queued} 个条目已排队更新，进度见任务面板。` })
  }
}

async function batchCheckVersion() {
  const targets = selectedSkills.value.filter((item) => item.provider !== 'local')
  let updates = 0; let skipped = selectedSkills.value.length - targets.length
  for (const item of targets) {
    try { const result = await api.checkVersion(item.name, item.library); if (result.has_update) updates += 1 } catch { skipped += 1 }
  }
  showToast({ type: updates ? 'warning' : 'success', message: `已完成 ${targets.length} 项版本检查：${updates} 项有更新${skipped ? `，跳过/失败 ${skipped} 项` : ''}。` })
}

async function batchDowngrade() {
  const targets = selectedSkills.value.filter((item) => item.item_type !== 'project' && item.provider !== 'local' && item.install_mode === 'full')
  if (!targets.length) { showToast({ type: 'warning', message: '所选条目中没有可降级为标准安装的项目。' }); return }
  let queued = 0; const failed = []
  for (const item of targets) {
    try { await api.changeMode(item.name, 'standard', item.library); queued += 1 } catch (error) { failed.push(`${item.name}：${error.message}`) }
  }
  await refreshSkills();
  showToast({ type: failed.length ? 'warning' : 'success', message: `已处理 ${queued} 项降级${failed.length ? `，失败 ${failed.length} 项` : ''}。` })
}

function requestBatchTrust() {
  const targets = selectedSkills.value.filter((item) => item.security_status === 'warning')
  if (!targets.length) {
    showToast({ type: 'warning', message: '所选条目中没有“需要确认”状态的技能。' })
    return
  }
  confirmState.value = {
    open: true,
    title: `批量信任 ${targets.length} 个技能？`,
    message: `将把所选的 ${targets.length} 个“需要确认”条目全部标记为信任来源。请确认这些来源（作者/仓库/用途）你都信任。`,
    confirmLabel: `信任 ${targets.length} 项`,
    tone: 'normal',
    action: performBatchTrust,
  }
}

async function performBatchTrust() {
  const targets = selectedSkills.value.filter((item) => item.security_status === 'warning')
  confirmState.value.open = false
  let done = 0
  for (const item of targets) {
    try {
      await api.trust(item.name, item.library)
      done += 1
    } catch (error) {
      showToast({ type: 'error', message: `${item.name} 信任失败：${error.message}` })
    }
  }
  if (done) {
    await refreshSkills()
    showToast({ type: 'success', message: `已信任 ${done} 个技能。` })
  }
}

function jobFinished(job) {
  if (job.status === 'error') {
    showToast({ type: 'error', message: `${job.label} 失败：${job.error}` })
    return
  }
  if (job.kind === 'scan') {
    refreshSkills(job.result?.name)
    showToast({
      type: job.result?.status === 'warning' ? 'warning' : 'success',
      message: `${job.result?.name} 安全检查完成${job.result?.status === 'warning' ? '，发现需要确认的问题。' : '。'}`,
    })
    return
  }
  if (job.kind === 'update') {
    refreshSkills(job.result?.skill?.name)
    showToast({
      type: 'success',
      message: job.result?.updated ? `${job.result?.skill?.name} 已更新。` : `${job.result?.skill?.name} 已是最新版本。`,
    })
    return
  }
  if (job.kind === 'translate') {
    refreshSkills()
    const result = job.result || {}
    if (result.failed) {
      showToast({
        type: 'warning',
        message: `备注翻译完成：成功 ${result.translated} 项，失败 ${result.failed} 项（${(result.failed_details || [])[0] || '详情见任务面板'}）。`,
      })
    } else {
      showToast({ type: 'success', message: `备注翻译完成：共翻译 ${result.translated || 0} 项。` })
    }
    return
  }
  installed(job.result)
}

function viewScanResult(job) {
  const result = job.result || {}
  // 新任务结果带 library，跨库同名可精确定位；旧结果没有时回退纯 name 匹配
  scanSkill.value = skills.value.find((item) => skillKey(item) === skillKey(result))
    || (result.library ? null : skills.value.find((item) => item.name === result.name))
    || { name: result.name, library: result.library, security_status: result.status }
  scanInitialReport.value = result
  scanOpen.value = true
}

function openScan(skill) {
  scanSkill.value = skill
  scanInitialReport.value = null
  scanOpen.value = true
}

async function scanFinished() {
  await refreshSkills(scanSkill.value ? skillKey(scanSkill.value) : '')
  if (detailOpen.value && scanSkill.value) {
    await selectSkill({ name: scanSkill.value.name, library: scanSkill.value.library })
  }
}

function scanClosed() {
  scanOpen.value = false
  scanInitialReport.value = null
}

function requestModeChange(skill) {
  if (skill.item_type === 'project') {
    showToast({ type: 'warning', message: '应用项目必须保留完整 Git 克隆，不能切换为技能安装模式。' })
    return
  }
  const nextMode = skill.install_mode === 'full' ? 'standard' : 'full'
  confirmState.value = {
    open: true,
    title: nextMode === 'full' ? '升级为全仓安装？' : '降级为标准安装？',
    message: nextMode === 'full'
      ? '将重新读取远端仓库并补齐全部文件。仓库内有手动修改时会先自动备份。'
      : '只会清理 manifest 记录中未被修改的多余文件；手动添加或改过的文件会保留并退出托管。',
    confirmLabel: nextMode === 'full' ? '确认升级' : '安全降级',
    tone: 'normal',
    action: () => performModeChange(skill, nextMode),
  }
}

async function performModeChange(skill, mode) {
  const result = await runAction(skill, 'mode', () => api.changeMode(skill.name, mode, skill.library))
  if (!result) return
  confirmState.value.open = false
  await refreshSkills(skillKey(skill))
  if (detailOpen.value) await selectSkill({ name: skill.name, library: skill.library })
  const preserved = result.preserved_files?.length || 0
  showToast({
    type: 'success',
    message: `${skill.name} 已切换为${mode === 'full' ? '全仓' : '标准'}安装${preserved ? `，并保留 ${preserved} 个手改文件` : ''}。`,
  })
}

function requestDelete(skill) {
  confirmState.value = {
    open: true,
    title: `删除 ${skill.name}？`,
    message: `该${skill.item_type === 'project' ? '应用项目' : '技能'}会从列表、SQLite 和 index.json 移除。文件移入仓库的 .meta/trash，避免误操作后无法恢复。`,
    confirmLabel: '完全删除',
    tone: 'danger',
    action: () => performDelete(skill),
  }
}

async function performDelete(skill) {
  const result = await runAction(skill, 'delete', () => api.remove(skill.name, skill.library))
  if (!result) return
  confirmState.value.open = false
  detailOpen.value = false
  selectedSkill.value = null
  await refreshSkills()
  showToast({ type: 'success', message: `${skill.name} 已删除，可从 .meta/trash 恢复。` })
}

async function installed(skill) {
  await refreshSkills(skill.name)
  showToast({
    type: skill.security_status === 'warning' ? 'warning' : 'success',
    message: skill.security_status === 'warning'
      ? `${skill.name} 已${skill.item_type === 'project' ? '克隆' : '入库'}，但安全检查发现需要确认的问题。`
      : `${skill.name} 已${skill.item_type === 'project' ? '完成项目克隆' : '安全入库'}。`,
  })
}

async function saveTags(skill, tags) {
  const result = await runAction(skill, 'tags', () => api.saveTags(skill.name, tags, skill.library))
  if (!result) return
  const nextKeys = tags.map((tag) => String(tag).toLocaleLowerCase())
  if (selectedTag.value === '__untagged__' && nextKeys.length) {
    selectedTag.value = `tag:${nextKeys[0]}`
  } else if (
    selectedTag.value.startsWith('tag:')
    && !nextKeys.includes(selectedTag.value.slice(4))
  ) {
    selectedTag.value = '__all__'
  }
  await refreshSkills(skillKey(skill))
  if (detailOpen.value) await selectSkill({ name: skill.name, library: skill.library })
  showToast({ type: 'success', message: `${skill.name} 的标签已保存。` })
}

async function translateSkill(skill) {
  const result = await runAction(skill, 'translate', () => api.translateOne(skill.name, skill.library))
  if (!result) return
  await refreshSkills(skillKey(result))
  if (detailOpen.value) await selectSkill({ name: result.name, library: result.library })
  const shown = result.description_zh || result.description
  showToast({
    type: 'success',
    message: result.description_zh
      ? `${result.name} 的中文备注：${shown.slice(0, 60)}${shown.length > 60 ? '…' : ''}`
      : `${result.name} 的备注已是中文，直接展示原文。`,
  })
}

function requestBatchTranslate() {
  const pending = skills.value.filter(
    (item) => item.description && !item.description_zh,
  ).length
  if (!pending) {
    showToast({ type: 'success', message: '所有条目都已有中文备注（或原生中文），无需翻译。' })
    return
  }
  confirmState.value = {
    open: true,
    title: `翻译 ${pending} 条备注？`,
    message: `将调用设置里的 AI 网关，把 ${pending} 条非中文且还没有译文的备注批量翻译成简体中文。已完成翻译或原生中文的条目会自动跳过，进度见右下角任务面板。`,
    confirmLabel: '开始翻译',
    tone: 'normal',
    action: performBatchTranslate,
  }
}

async function performBatchTranslate() {
  confirmState.value.open = false
  try {
    await api.startTranslate(null)
    wakeJobPolling()
    showToast({ type: 'success', message: '翻译任务已转入后台，进度见右下角任务面板。' })
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  }
}

async function saveMetadata(skill, payload) {
  const result = await runAction(skill, 'meta', () => api.updateMetadata(skill.name, payload, skill.library))
  if (!result) return
  const renamed = result.name !== skill.name
  await refreshSkills(skillKey(result))
  if (detailOpen.value) await selectSkill({ name: result.name, library: result.library })
  showToast({ type: 'success', message: `${result.name} 的信息已保存${renamed ? `（原条目名 ${skill.name}）` : ''}。` })
}

async function settingsSaved(nextConfig) {
  config.value = { ...nextConfig, ai_presets: config.value.ai_presets || [] }
  health.value.configured = Boolean(nextConfig.repo_root)
  await refreshSkills()
  view.value = 'library'
}

async function repositoryReconciled() {
  await refreshSkills()
  // 导入等操作会同时改变记忆库：导航徽章一并刷新
  try {
    memoryStats.value = await api.memoryStats()
  } catch {
    /* 记忆统计失败不阻断技能刷新 */
  }
}

async function openFolder(path) {
  try {
    await api.openDirectory(path)
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  }
}

function currentBusy(skill) {
  return busySkillName.value === skill.name ? busyAction.value : ''
}
</script>

<template>
  <div v-if="loading" class="app-loading">
    <img class="brand-logo brand-logo-lg" :src="theme === 'dark' ? logoHeiUrl : logoUrl" alt="123mshub" />
    <div class="loading-lines"><span></span><span></span></div>
  </div>

  <div v-else-if="fatalError" class="fatal-state">
    <img class="brand-logo brand-logo-lg" :src="theme === 'dark' ? logoHeiUrl : logoUrl" alt="123mshub" />
    <h1>无法连接本地服务</h1>
    <p>{{ fatalError }}</p>
    <button class="primary-button" type="button" @click="loadApp">重新连接</button>
  </div>

  <div v-else class="app-shell" :class="{ 'has-tasks': jobStore.items.length > 0 }">
    <aside class="sidebar" :class="{ 'mobile-open': mobileNavOpen }">
      <div class="brand-lockup">
        <img class="brand-logo" :src="theme === 'dark' ? logoHeiUrl : logoUrl" alt="123 MSHub" />
        <div><strong>123 MSHub</strong><span>本地共享大脑管理器</span></div>
        <button class="mobile-close" type="button" aria-label="关闭导航" @click="mobileNavOpen = false">
          <X :size="20" />
        </button>
      </div>

      <nav class="main-nav" aria-label="主导航">
        <button :class="{ active: view === 'memory' }" type="button" @click="navigate('memory')">
          <Brain :size="18" /><span>记忆库</span>
          <b v-if="memoryStats.inbox_pending" class="nav-pending-badge">{{ memoryStats.inbox_pending }}</b>
          <b v-else>{{ memoryStats.total }}</b>
        </button>
        <button :class="{ active: view === 'graph' }" type="button" @click="navigate('graph')">
          <Tags :size="18" /><span>记忆图示</span><b>{{ memoryStats.total }}</b>
        </button>
        <button :class="{ active: view === 'library' }" type="button" @click="navigate('library')">
          <Archive :size="18" /><span>技能库</span><b>{{ skills.length }}</b>
        </button>
        <button :class="{ active: view === 'security' }" type="button" @click="navigate('security')">
          <ShieldCheck :size="18" /><span>安全中心</span><b v-if="warningCount">{{ warningCount }}</b>
        </button>
        <button :class="{ active: view === 'settings' }" type="button" @click="navigate('settings')">
          <Settings :size="18" /><span>设置</span>
        </button>
      </nav>

      <div class="sidebar-repo" v-if="health.configured">
        <span>当前仓库</span>
        <button type="button" title="在资源管理器中打开" @click="openFolder(config.repo_root)">
          <FolderOpen :size="16" />
          <span>{{ config.repo_root }}</span>
        </button>
        <div><span>{{ skills.length }} 个条目</span><span>{{ safeCount }} 个已通过检查</span></div>
      </div>

      <div class="sidebar-share" v-if="health.configured">
        <button type="button" class="share-prompt-button" @click="copyInjectionPrompt">
          <ClipboardCopy :size="16" />
          <span>复制注入提示词</span>
        </button>
        <p>发给任意本地 Agent：教它读共享记忆、用共享技能库、往 inbox 投递新记忆。</p>
      </div>

      <div class="sidebar-footer">
        <a href="/api/docs" target="_blank"><BookOpenText :size="16" /> API 文档</a>
        <a href="/api/help" target="_blank"><CircleHelp :size="16" /> 使用说明</a>
        <button
          class="theme-toggle"
          type="button"
          :aria-label="theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'"
          @click="toggleTheme"
        >
          <Transition name="theme-icon" mode="out-in">
            <Sun v-if="theme === 'dark'" :size="16" key="sun" />
            <Moon v-else :size="16" key="moon" />
          </Transition>
          <span>{{ theme === 'dark' ? '切换亮色模式' : '切换暗色模式' }}</span>
        </button>
      </div>
    </aside>

    <div v-if="mobileNavOpen" class="mobile-nav-backdrop" @click="mobileNavOpen = false"></div>

    <main class="main-content">
      <button class="mobile-menu" type="button" aria-label="打开导航" @click="mobileNavOpen = true">
        <Menu :size="20" />
      </button>

      <section v-if="view === 'library'" class="library-view">
        <header class="view-heading library-heading">
          <div>
            <h1>技能库</h1>
            <p>统一管理 Agent 技能和可持续更新的应用程序项目，全部条目共享给接入的 agent。</p>
          </div>
          <div class="heading-actions">
            <button class="secondary-button" type="button" @click="copyInjectionPrompt">
              <ClipboardCopy :size="16" /> 复制注入提示词
            </button>
            <button class="primary-button add-skill-button" type="button" @click="addOpen = true">
              <PackagePlus :size="17" /> 添加技能或项目
            </button>
          </div>
        </header>

        <div class="toolbar">
          <label class="search-field">
            <Search :size="17" />
            <input v-model="search" placeholder="搜索技能、项目、作者或功能说明" aria-label="搜索技能与项目" />
            <button v-if="search" type="button" aria-label="清除搜索" @click="search = ''"><X :size="15" /></button>
          </label>
          <label class="filter-select">
            <span>安全状态</span>
            <select v-model="statusFilter">
              <option value="all">全部状态</option>
              <option value="safe">安全无风险</option>
              <option value="warning">需要确认</option>
              <option value="unchecked">尚未检查</option>
            </select>
            <ChevronDown :size="15" />
          </label>
          <label class="filter-select"><span>来源</span><select v-model="sourceFilter"><option value="all">全部来源</option><option value="local">本地自研</option><option value="github">GitHub 源</option><option v-for="item in [...new Set(skills.map((skill) => skill.imported_from).filter(Boolean))]" :key="item" :value="`from:${item}`">来自 {{ item }}</option></select><ChevronDown :size="15" /></label>
          <label class="filter-select"><span>类别</span><select v-model="assetFilter"><option value="all">程序与技能</option><option value="skill">技能</option><option value="project">程序</option></select><ChevronDown :size="15" /></label>
          <button
            class="secondary-button batch-toggle"
            :class="{ active: selectionMode }"
            type="button"
            @click="toggleSelectionMode"
          >
            <ListCheck :size="16" /> {{ selectionMode ? '退出多选' : '多选' }}
          </button>
          <button
            class="secondary-button"
            type="button"
            title="把非中文备注批量翻译成简体中文（调用设置里的 AI 网关）"
            @click="requestBatchTranslate"
          >
            <Languages :size="16" /> 翻译备注
          </button>
        </div>
        <div v-if="skills.length" class="tag-filter-bar" :class="{ expanded: tagsExpanded }" aria-label="按标签筛选">
          <span class="tag-filter-label"><Tags :size="15" /> 分类</span>
          <div class="tag-filter-scroll">
            <button
              type="button"
              :class="{ active: selectedTag === '__all__' }"
              @click="selectedTag = '__all__'"
            >
              全部 <b>{{ skills.length }}</b>
            </button>
            <button
              v-for="tag in tagOptions"
              :key="tag.key"
              type="button"
              :class="{ active: selectedTag === `tag:${tag.key}` }"
              @click="selectedTag = `tag:${tag.key}`"
            >
              #{{ tag.name }} <b>{{ tag.count }}</b>
            </button>
            <button
              v-if="untaggedCount"
              type="button"
              :class="{ active: selectedTag === '__untagged__' }"
              @click="selectedTag = '__untagged__'"
            >
              未标记 <b>{{ untaggedCount }}</b>
            </button>
            <button class="tag-expand-button" type="button" @click="toggleTagsExpanded">{{ tagsExpanded ? '收起标签' : '展开全部标签' }}</button>
          </div>
        </div>

        <div v-if="selectionMode" class="batch-bar" role="region" aria-label="批量操作">
          <label class="batch-select-all" @click.prevent="selectAllFiltered">
            <CheckSquare :size="16" />
            <span>全选当前 {{ filteredSkills.length }} 项</span>
          </label>
          <span class="batch-count">已选 <b>{{ selectedNames.length }}</b></span>
          <div class="batch-actions">
            <button class="secondary-button" type="button" :disabled="!selectedNames.length" title="跳过本地自研项目" @click="batchCheckVersion"><Search :size="15" /> 查版本</button>
            <button class="secondary-button" type="button" :disabled="!selectedNames.length" @click="batchScan">
              <ShieldCheck :size="15" /> 批量安全检查
            </button>
            <button class="secondary-button" type="button" :disabled="!selectedNames.length" @click="batchUpdate">
              <RefreshCw :size="15" /> 批量更新
            </button>
            <button class="secondary-button" type="button" :disabled="!selectedNames.length" title="仅处理全仓技能，自动跳过本地自研和程序项目" @click="batchDowngrade"><ArrowDownCircle :size="15" /> 降级标准</button>
            <button
              class="trust-button"
              type="button"
              :disabled="!selectedWarningCount"
              :title="selectedWarningCount ? `信任其中 ${selectedWarningCount} 个待确认项` : '所选没有待确认项'"
              @click="requestBatchTrust"
            >
              信任待确认项
            </button>
          </div>
        </div>

        <div v-if="skills.length" class="list-header" aria-hidden="true">
          <span>技能、项目与说明</span><span>类型 / 版本 / 安全</span><span>操作</span>
        </div>

        <div v-if="filteredSkills.length" class="skill-list" @pointerdown="selectionStart" @pointermove="selectionMove" @pointerup="selectionEnd" @pointercancel="selectionEnd">
          <div v-if="selectionBox" class="selection-rect" :style="{ left: `${selectionBox.left}px`, top: `${selectionBox.top}px`, width: `${selectionBox.width}px`, height: `${selectionBox.height}px` }" aria-hidden="true"></div>
          <SkillRow
            v-for="skill in filteredSkills"
            :key="skillKey(skill)"
            :skill="skill"
            :busy-action="currentBusy(skill)"
            :selectable="selectionMode"
            :selected="selectedNames.includes(skillKey(skill))"
            @select="selectSkill"
            @copy="copyPrompt"
            @check="checkVersion"
            @update="updateSkill"
            @scan="openScan"
            @menu="requestModeChange"
            @toggle-select="toggleSelected"
            @trust="requestTrust"
          />
        </div>
        <EmptyState
          v-else
          :filtered="Boolean(filterActive)"
          @add="addOpen = true"
          @clear="clearFilters"
        />
      </section>

      <MemoryView
        v-else-if="view === 'memory'"
        :enabled="health.configured"
        @toast="showToast"
        @copy-prompt="copyInjectionPrompt"
        @stats="memoryStats = $event"
        @confirm="(state) => confirmState = state"
      />

      <MemoryGraph
        v-else-if="view === 'graph'"
        @open="(name) => { view = 'memory'; $nextTick(() => document.dispatchEvent(new CustomEvent('mshub:open-memory', { detail: name }))) }"
        @toast="showToast"
      />

      <SecurityView
        v-else-if="view === 'security'"
        :skills="skills"
        @scan="openScan"
        @select="selectSkill"
        @trust="requestTrust"
      />

      <SettingsView
        v-else
        :key="config.repo_root || 'first-run'"
        :config="config"
        :first-run="!health.configured"
        @saved="settingsSaved"
        @updated="config = { ...$event, ai_presets: config.ai_presets || [] }"
        @reconciled="repositoryReconciled"
        @toast="showToast"
      />
    </main>

    <AddSkillModal
      :open="addOpen"
      :tag-suggestions="tagSuggestions"
      :libraries="health.libraries || []"
      :multi-library="Boolean(health.multi_library)"
      @close="addOpen = false"
      @toast="showToast"
    />
    <ScanModal
      :open="scanOpen"
      :skill="scanSkill"
      :config="config"
      :initial-report="scanInitialReport"
      @close="scanClosed"
      @scanned="scanFinished"
      @trust="requestTrust"
    />
    <DetailDrawer
      :open="detailOpen"
      :skill="selectedSkill"
      :busy-action="selectedSkill ? currentBusy(selectedSkill) : ''"
      :loading="detailLoading"
      :tag-suggestions="tagSuggestions"
      @close="detailOpen = false"
      @copy="copyPrompt"
      @check="checkVersion"
      @update="updateSkill"
      @scan="openScan"
      @mode="requestModeChange"
      @remove="requestDelete"
      @open-folder="openFolder"
      @save-tags="saveTags"
      @save-meta="saveMetadata"
      @translate="translateSkill"
      @trust="requestTrust"
    />
    <Transition name="modal">
      <div v-if="batchScanOpen" class="modal-backdrop" @mousedown.self="batchScanOpen = false">
        <section class="modal-panel batch-scan-dialog" role="dialog" aria-modal="true" aria-labelledby="batch-scan-title">
          <header class="modal-header"><div><span class="step-label">批量安全检查</span><h2 id="batch-scan-title">选择检查线路</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="batchScanOpen = false"><X :size="20" /></button></header>
          <div class="modal-body"><p>已选择 {{ selectedSkills.length }} 项。每个条目都会独立排队，失败项目不会阻断其他项目。</p><div class="scan-route-grid"><button type="button" class="scan-route" :class="{ selected: batchScanRoute === 'offline' }" @click="batchScanRoute = 'offline'"><strong>路线 A · 普通检查</strong><p>离线、免费，检查危险脚本和提示词注入。</p></button><button type="button" class="scan-route" :class="{ selected: batchScanRoute === 'ai' }" @click="batchScanRoute = 'ai'"><strong>路线 B · AI 深度审查</strong><p>使用设置里的 API，按量计费并可能需要联网。</p></button></div></div>
          <footer class="modal-footer"><button class="secondary-button" type="button" @click="batchScanOpen = false">取消</button><button class="primary-button" type="button" @click="runBatchScan">开始检查</button></footer>
        </section>
      </div>
    </Transition>
    <ConfirmModal
      :open="confirmState.open"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-label="confirmState.confirmLabel"
      :tone="confirmState.tone"
      :busy="busyAction === 'mode' || busyAction === 'delete'"
      @close="confirmState.open = false"
      @confirm="confirmState.action?.()"
    />

    <TaskPanel @view-scan="viewScanResult" />

    <Transition name="toast">
      <div v-if="toast" class="toast-message" :class="`toast-${toast.type}`" role="status">
        <span></span>
        <p>{{ toast.message }}</p>
        <button type="button" aria-label="关闭消息" @click="toast = null"><X :size="16" /></button>
      </div>
    </Transition>
  </div>
</template>
