<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { Filter, Maximize2, RefreshCw, Search, Settings, X } from '@lucide/vue'
import Graph from 'graphology'
import FA2Layout from 'graphology-layout-forceatlas2/worker'
import Sigma from 'sigma'
import { drawDiscNodeLabel, NodeCircleProgram } from 'sigma/rendering'
import { api } from '../api'

const emit = defineEmits(['open', 'toast'])

const GRAPH_SETTINGS_KEY = 'mshub.memoryGraph.settings.v1'
const GRAPH_DEFAULTS = {
  includeTags: false,
  showOrphans: true,
  labelThreshold: 8,
  nodeScale: 1,
  selectedTypes: { user: true, project: true, reference: true, feedback: true },
  forces: { center: 1, repel: 100, link: 1, distance: 80 },
}

function readGraphSettings() {
  if (typeof window === 'undefined') return {}
  try {
    const stored = window.localStorage.getItem(GRAPH_SETTINGS_KEY)
    const parsed = stored ? JSON.parse(stored) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function numericSetting(value, fallback, min, max) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.min(max, Math.max(min, number))
}

const persistedSettings = readGraphSettings()
const surfaceRef = ref(null)
const containerRef = ref(null)
const tooltipRef = ref(null)
const loading = ref(true)
const error = ref('')
const raw = ref({ nodes: [], edges: [] })
const query = ref('')
const includeTags = ref(Boolean(persistedSettings.includeTags ?? GRAPH_DEFAULTS.includeTags))
const showOrphans = ref(persistedSettings.showOrphans !== false)
const settingsOpen = ref(false)
const hovered = ref(null)
const tooltip = ref(null)
const labelThreshold = ref(numericSetting(persistedSettings.labelThreshold, GRAPH_DEFAULTS.labelThreshold, 2, 18))
const nodeScale = ref(numericSetting(persistedSettings.nodeScale, GRAPH_DEFAULTS.nodeScale, 0.6, 1.8))
const selectedTypes = reactive({
  ...GRAPH_DEFAULTS.selectedTypes,
  ...(persistedSettings.selectedTypes || {}),
})
const forces = reactive({
  center: numericSetting(persistedSettings.forces?.center, GRAPH_DEFAULTS.forces.center, 0.1, 4),
  repel: numericSetting(persistedSettings.forces?.repel, GRAPH_DEFAULTS.forces.repel, 20, 220),
  link: numericSetting(persistedSettings.forces?.link, GRAPH_DEFAULTS.forces.link, 0, 2),
  distance: numericSetting(persistedSettings.forces?.distance, GRAPH_DEFAULTS.forces.distance, 40, 160),
})

let graph = null
let renderer = null
let layout = null
let layoutStopTimer = null
let draggedNode = null
let dragPosition = null
let destroyed = false
let loadSequence = 0
let hoveredNeighbors = new Set()
let themeObserver = null
let graphTheme = {
  background: '#171717',
  label: '#d8d8d8',
  dimNode: '#232323',
  dimEdge: '#222222',
  focusEdge: '#4a4a4a',
  tagEdge: '#3f3f3f',
}

const typeColors = {
  user: '#a78bfa',
  project: '#6ea8fe',
  reference: '#77c5d5',
  feedback: '#e3a85b',
}
const typeLabels = {
  user: '用户',
  project: '项目',
  reference: '参考',
  feedback: '反馈',
}
const nodeProgramClasses = {
  user: NodeCircleProgram,
  project: NodeCircleProgram,
  reference: NodeCircleProgram,
  feedback: NodeCircleProgram,
}

function parseColor(value) {
  const input = String(value || '').trim()
  const hex = input.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (hex) {
    const raw = hex[1].length === 3
      ? hex[1].split('').map((part) => `${part}${part}`).join('')
      : hex[1]
    return {
      r: Number.parseInt(raw.slice(0, 2), 16),
      g: Number.parseInt(raw.slice(2, 4), 16),
      b: Number.parseInt(raw.slice(4, 6), 16),
    }
  }
  const rgb = input.match(/^rgba?\(([^)]+)\)$/i)
  if (!rgb) return null
  const parts = rgb[1].split(',').map((part) => part.trim())
  if (parts.length < 3) return null
  const values = parts.slice(0, 3).map((part) => {
    if (part.endsWith('%')) return Math.round((Number.parseFloat(part) / 100) * 255)
    return Number.parseFloat(part)
  })
  if (values.some((part) => !Number.isFinite(part))) return null
  return { r: values[0], g: values[1], b: values[2] }
}

function toHex(value) {
  return Math.min(255, Math.max(0, Math.round(value))).toString(16).padStart(2, '0')
}

// Sigma's WebGL colors are opaque after conversion. Mix with the actual
// canvas background to reproduce Obsidian-like alpha without rgba artifacts.
function blendToBackground(foreground, ratio, background) {
  const fg = parseColor(foreground) || { r: 166, g: 166, b: 166 }
  const bg = parseColor(background) || { r: 23, g: 23, b: 23 }
  const amount = Math.min(1, Math.max(0, Number(ratio) || 0))
  return `#${toHex(fg.r * amount + bg.r * (1 - amount))}${toHex(fg.g * amount + bg.g * (1 - amount))}${toHex(fg.b * amount + bg.b * (1 - amount))}`
}

function refreshGraphTheme() {
  if (!surfaceRef.value) return
  const styles = getComputedStyle(surfaceRef.value)
  const background = styles.backgroundColor || '#171717'
  const label = styles.getPropertyValue('--graph-label').trim() || '#d8d8d8'
  graphTheme = {
    background,
    label,
    dimNode: blendToBackground('#a6a6a6', 0.10, background),
    dimEdge: blendToBackground('#8c8c8c', 0.12, background),
    focusEdge: blendToBackground('#8c8c8c', 0.45, background),
    tagEdge: blendToBackground('#b4b4b4', 0.30, background),
  }
  if (renderer) renderer.setSetting('labelColor', { color: graphTheme.label })
}

function persistGraphSettings() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(GRAPH_SETTINGS_KEY, JSON.stringify({
      includeTags: includeTags.value,
      showOrphans: showOrphans.value,
      labelThreshold: labelThreshold.value,
      nodeScale: nodeScale.value,
      selectedTypes: { ...selectedTypes },
      forces: { ...forces },
    }))
  } catch {
    // Private browsing or a locked-down WebView may disable localStorage.
  }
}

const nodeCount = computed(() => raw.value.nodes.length)
const edgeCount = computed(() => raw.value.edges.length)
const hasData = computed(() => nodeCount.value > 0)

function stableHash(value) {
  let hash = 2166136261
  for (const char of String(value)) {
    hash ^= char.codePointAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function seededPosition(id, index) {
  // Deterministic pseudo-random points avoid a visual ring/grid pattern and
  // make refreshes stable before the worker begins relaxing the graph.
  const first = stableHash(`${id}:x:${index}`) / 0xffffffff
  const second = stableHash(`${id}:y:${index}`) / 0xffffffff
  return { x: (first * 2 - 1) * 4, y: (second * 2 - 1) * 4 }
}

function edgeKey(source, target, kind = '双链') {
  const pair = [String(source), String(target)].sort()
  return `${kind}:${pair[0]}::${pair[1]}`
}

function distanceWeightMultiplier() {
  const distance = numericSetting(forces.distance, GRAPH_DEFAULTS.forces.distance, 40, 160)
  return 2 - (distance / 160) * 1.5
}

function normalizedNode(node, index) {
  const id = String(node.id || node.name || `memory-${index}`)
  const position = seededPosition(id, index)
  const requestedType = String(node.type || 'reference')
  const type = Object.prototype.hasOwnProperty.call(typeColors, requestedType)
    ? requestedType
    : 'reference'
  return {
    id,
    label: String(node.title || node.id || id),
    title: String(node.title || node.id || id),
    type,
    source: String(node.source || ''),
    tags: Array.isArray(node.tags) ? node.tags : [],
    x: Number.isFinite(node.x) ? node.x : position.x,
    y: Number.isFinite(node.y) ? node.y : position.y,
    color: typeColors[type],
  }
}

function queryMatches(node, nodeId = '') {
  const term = query.value.trim().toLocaleLowerCase()
  if (!term) return true
  return [nodeId, node.id, node.title, node.source, ...(node.tags || [])]
    .some((value) => String(value || '').toLocaleLowerCase().includes(term))
}

function nodeFilterState(node, nodeId = '') {
  const typeVisible = selectedTypes[node.type] !== false
  const orphanVisible = showOrphans.value || !graph || !nodeId || graph.degree(nodeId) > 0
  return {
    structuralVisible: typeVisible && orphanVisible,
    queryMatch: queryMatches(node, nodeId),
  }
}

function isNeighbor(node) {
  return !hovered.value || node === hovered.value || hoveredNeighbors.has(node)
}

function nodeReducer(node, data) {
  const { structuralVisible, queryMatch } = nodeFilterState(data, node)
  const focused = !hovered.value || isNeighbor(node)
  const degree = graph?.degree(node) || 0
  const size = (4 + Math.sqrt(degree) * 2) * nodeScale.value
  const dimmed = !queryMatch || !focused
  return {
    ...data,
    size,
    label: !dimmed ? data.label : null,
    hidden: !structuralVisible,
    color: dimmed ? graphTheme.dimNode : data.color,
    forceLabel: node === hovered.value,
  }
}

function edgeReducer(edge, data) {
  const [source, target] = graph.extremities(edge)
  const sourceState = nodeFilterState(graph.getNodeAttributes(source), source)
  const targetState = nodeFilterState(graph.getNodeAttributes(target), target)
  const structuralVisible = sourceState.structuralVisible && targetState.structuralVisible
  const queryMatch = sourceState.queryMatch && targetState.queryMatch
  const linkedToHovered = Boolean(hovered.value && (source === hovered.value || target === hovered.value))
  const hoveredNode = hovered.value && graph.hasNode(hovered.value)
    ? graph.getNodeAttributes(hovered.value)
    : null
  const color = !queryMatch
    ? graphTheme.dimEdge
    : linkedToHovered
      ? blendToBackground(hoveredNode?.color || '#a6a6a6', 0.60, graphTheme.background)
      : hovered.value
        ? graphTheme.dimEdge
        : data.kind === '共同标签' ? graphTheme.tagEdge : graphTheme.focusEdge
  return {
    ...data,
    hidden: !structuralVisible,
    color,
    size: linkedToHovered ? 1.6 : queryMatch ? 1 : 0.7,
  }
}

function drawMemoryLabel(context, data, settings) {
  if (!data.label) return
  const size = settings.labelSize
  const font = settings.labelFont
  const weight = settings.labelWeight
  context.save()
  context.font = `${weight} ${size}px ${font}`
  context.lineJoin = 'round'
  context.lineWidth = 4
  context.strokeStyle = graphTheme.background
  context.strokeText(data.label, data.x + data.size + 3, data.y + size / 3)
  // Keep Sigma's exact baseline and color handling after drawing the halo.
  drawDiscNodeLabel(context, data, settings)
  context.restore()
}

function drawMemoryHover(context, data) {
  context.save()
  context.beginPath()
  context.arc(data.x, data.y, data.size + 5, 0, Math.PI * 2)
  context.fillStyle = 'rgba(180,180,180,.16)'
  context.shadowBlur = 14
  context.shadowColor = data.color || '#a6a6a6'
  context.fill()
  context.restore()
}

function syncGraph(data) {
  if (!graph) graph = new Graph({ type: 'undirected', multi: true })
  const nextNodes = new Map((data.nodes || []).map((node, index) => {
    const item = normalizedNode(node, index)
    return [item.id, item]
  }))
  for (const id of graph.nodes()) {
    if (!nextNodes.has(id)) graph.dropNode(id)
  }
  nextNodes.forEach((item) => {
    if (graph.hasNode(item.id)) {
      const current = graph.getNodeAttributes(item.id)
      graph.mergeNodeAttributes(item.id, {
        ...item,
        x: Number.isFinite(current.x) ? current.x : item.x,
        y: Number.isFinite(current.y) ? current.y : item.y,
      })
    } else {
      graph.addNode(item.id, item)
    }
  })

  const nextEdges = new Map()
  for (const edge of data.edges || []) {
    const source = String(edge.source)
    const target = String(edge.target)
    if (!graph.hasNode(source) || !graph.hasNode(target) || source === target) continue
    const kind = edge.kind || '双链'
    const key = edgeKey(source, target, kind)
    const baseWeight = kind === '共同标签' ? 0.5 : 2
    nextEdges.set(key, { source, target, kind, weight: baseWeight * distanceWeightMultiplier() })
  }
  for (const edge of graph.edges()) {
    if (!nextEdges.has(edge)) graph.dropEdge(edge)
  }
  nextEdges.forEach((item, key) => {
    if (!graph.hasEdge(key)) {
      graph.addEdgeWithKey(key, item.source, item.target, {
        kind: item.kind,
        size: 1,
        weight: item.weight,
      })
    } else {
      graph.mergeEdgeAttributes(key, { kind: item.kind, weight: item.weight })
    }
  })
}

function stopLayoutTimer() {
  if (layoutStopTimer) window.clearTimeout(layoutStopTimer)
  layoutStopTimer = null
}

function scheduleLayoutStop() {
  stopLayoutTimer()
  if (!layout || !graph) return
  layoutStopTimer = window.setTimeout(() => {
    layout?.stop()
    renderer?.refresh()
  }, graph.order > 1800 ? 2600 : 1800)
}

function reheatLayout() {
  if (!layout) return
  stopLayoutTimer()
  layout.start()
}

function applyEdgeWeights() {
  if (!graph) return
  const multiplier = distanceWeightMultiplier()
  graph.forEachEdge((edge, attributes) => {
    const baseWeight = attributes.kind === '共同标签' ? 0.5 : 2
    graph.setEdgeAttribute(edge, 'weight', baseWeight * multiplier)
  })
}

function restartLayout(resetPositions = false) {
  stopLayoutTimer()
  layout?.kill()
  layout = null
  if (!graph || graph.order < 2) return
  if (resetPositions) {
    graph.forEachNode((id) => {
      const position = seededPosition(id, stableHash(id) % 997)
      graph.mergeNodeAttributes(id, { x: position.x, y: position.y })
    })
  }
  layout = new FA2Layout(graph, {
    // The worker owns its position matrix. Feed the pointer position back after
    // each iteration so it cannot overwrite a drag and neighbors feel the pull.
    outputReducer: (node, attributes) => node === draggedNode && dragPosition
      ? { ...attributes, ...dragPosition }
      : attributes,
    settings: {
      gravity: Number(forces.center),
      scalingRatio: Number(forces.repel),
      slowDown: 1,
      barnesHutOptimize: true,
      barnesHutTheta: 0.5,
      edgeWeightInfluence: Number(forces.link),
      adjustSizes: true,
    },
  })
  layout.start()
  // Keep the worker bounded: the view remains interactive while it settles,
  // and no background worker survives a page switch.
  scheduleLayoutStop()
}

function refreshRenderer() {
  refreshGraphTheme()
  if (!renderer) return
  renderer.setSetting('labelRenderedSizeThreshold', Number(labelThreshold.value))
  renderer.setSetting('hideEdgesOnMove', Boolean(graph && graph.size > 8000))
  renderer.refresh()
}

function updateTooltip(node, event) {
  if (!graph || !graph.hasNode(node)) return
  const attrs = graph.getNodeAttributes(node)
  const position = clampTooltipPosition(event?.x || 0, event?.y || 0)
  const title = attrs.title
  tooltip.value = {
    x: position.x,
    y: position.y,
    title,
    type: typeLabels[attrs.type] || attrs.type,
    tags: attrs.tags?.join('、') || '无标签',
    connections: graph.degree(node),
  }
  nextTick(() => {
    if (!tooltip.value || tooltip.value.title !== title) return
    const nextPosition = clampTooltipPosition(event?.x || 0, event?.y || 0)
    if (tooltip.value.x !== nextPosition.x || tooltip.value.y !== nextPosition.y) {
      tooltip.value = { ...tooltip.value, ...nextPosition }
    }
  })
}

function clampTooltipPosition(x, y) {
  const surface = surfaceRef.value
  if (!surface) return { x, y }
  const margin = 12
  const offset = 10
  const width = tooltipRef.value?.offsetWidth || 260
  const height = tooltipRef.value?.offsetHeight || 82
  const maxX = Math.max(margin, surface.clientWidth - width - margin - offset)
  const maxY = Math.max(margin, surface.clientHeight - height - margin - offset)
  return {
    x: Math.min(maxX, Math.max(margin, Number(x) || 0)),
    y: Math.min(maxY, Math.max(margin, Number(y) || 0)),
  }
}

function clearHover() {
  hovered.value = null
  hoveredNeighbors.clear()
  tooltip.value = null
}

function bindRenderer() {
  if (!renderer) return
  renderer.on('enterNode', ({ node, event }) => {
    hovered.value = node
    hoveredNeighbors = new Set([node, ...graph.neighbors(node)])
    updateTooltip(node, event)
    renderer.refresh()
  })
  renderer.on('leaveNode', () => {
    clearHover()
    renderer.refresh()
  })
  renderer.on('clickNode', ({ node }) => emit('open', node))
  renderer.on('clickStage', () => { clearHover(); renderer.refresh() })
  renderer.on('doubleClickStage', () => renderer.getCamera().animatedReset({ duration: 300 }))
  renderer.on('downNode', ({ node, event }) => {
    draggedNode = node
    const { x, y } = graph.getNodeAttributes(node)
    dragPosition = { x, y }
    reheatLayout()
    renderer.getCamera().disable()
    event.preventSigmaDefault()
    event.original.preventDefault()
  })
  renderer.getMouseCaptor().on('mousemovebody', (event) => {
    if (draggedNode) {
      const position = renderer.viewportToGraph(event)
      dragPosition = position
      graph.setNodeAttribute(draggedNode, 'x', position.x)
      graph.setNodeAttribute(draggedNode, 'y', position.y)
      event.preventSigmaDefault()
      event.original.preventDefault()
      renderer.refresh()
    } else if (hovered.value) {
      updateTooltip(hovered.value, event)
    }
  })
  renderer.getMouseCaptor().on('mouseup', () => {
    if (!draggedNode) return
    draggedNode = null
    dragPosition = null
    renderer.getCamera().enable()
    scheduleLayoutStop()
  })
}

async function load() {
  if (destroyed) return
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  try {
    const result = await api.memoryGraph(includeTags.value ? 'link,tag' : 'link')
    if (destroyed || sequence !== loadSequence) return
    stopLayoutTimer()
    layout?.kill()
    layout = null
    clearHover()
    raw.value = result
    syncGraph(result)
    refreshGraphTheme()
    await nextTick()
    if (destroyed || sequence !== loadSequence) return
    if (!renderer && containerRef.value && graph) {
      renderer = new Sigma(graph, containerRef.value, {
        renderLabels: true,
        labelFont: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        labelSize: 12,
        labelWeight: '500',
        labelColor: { color: graphTheme.label },
        labelRenderedSizeThreshold: Number(labelThreshold.value),
        labelDensity: 0.8,
        labelGridCellSize: 80,
        defaultNodeColor: '#a6a6a6',
        defaultEdgeColor: graphTheme.focusEdge,
        defaultNodeType: 'circle',
        // Sigma treats the node `type` attribute as a renderer key. The
        // graph uses semantic types for filtering, so map each one to the
        // built-in circle program instead of asking Sigma for a program named
        // "project", "reference", etc.
        nodeProgramClasses,
        defaultDrawNodeLabel: drawMemoryLabel,
        defaultDrawNodeHover: drawMemoryHover,
        nodeReducer,
        edgeReducer,
        hideEdgesOnMove: graph.size > 8000,
        hideLabelsOnMove: false,
        stagePadding: 28,
        zIndex: true,
      })
      bindRenderer()
    } else if (renderer) {
      renderer.setGraph(graph)
      refreshRenderer()
    }
    applyEdgeWeights()
    restartLayout(false)
  } catch (loadError) {
    if (destroyed || sequence !== loadSequence) return
    error.value = loadError.message || '记忆图谱读取失败。'
  } finally {
    if (!destroyed && sequence === loadSequence) loading.value = false
  }
}

function resetView() { renderer?.getCamera().animatedReset({ duration: 300 }) }
function zoomIn() { renderer?.getCamera().animatedZoom({ factor: 0.75, duration: 220 }) }
function zoomOut() { renderer?.getCamera().animatedUnzoom({ factor: 0.75, duration: 220 }) }
function applyForceChange() {
  applyEdgeWeights()
  persistGraphSettings()
  restartLayout(false)
}

watch([query, showOrphans, () => selectedTypes.user, () => selectedTypes.project, () => selectedTypes.reference, () => selectedTypes.feedback], () => {
  refreshRenderer()
})
watch(includeTags, load)
watch([nodeScale, labelThreshold], refreshRenderer)
watch([
  includeTags,
  showOrphans,
  labelThreshold,
  nodeScale,
  () => selectedTypes.user,
  () => selectedTypes.project,
  () => selectedTypes.reference,
  () => selectedTypes.feedback,
  () => forces.center,
  () => forces.repel,
  () => forces.link,
  () => forces.distance,
], persistGraphSettings)

onMounted(() => {
  refreshGraphTheme()
  if (typeof MutationObserver !== 'undefined') {
    themeObserver = new MutationObserver(() => refreshRenderer())
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  }
  load()
})
onUnmounted(() => {
  destroyed = true
  persistGraphSettings()
  themeObserver?.disconnect()
  stopLayoutTimer()
  layout?.kill()
  renderer?.kill()
})
</script>

<template>
  <section class="memory-graph-view">
    <header class="view-heading graph-header">
      <div>
        <span class="eyebrow">OBSIDIAN GRAPH VIEW</span>
        <h1>记忆图示</h1>
        <p>双链关系在画布上自然展开；悬停节点查看一度关联，滚轮缩放，拖动节点整理空间。</p>
      </div>
      <div class="graph-stats" aria-live="polite">
        <strong>{{ nodeCount }}</strong><span>节点</span>
        <strong>{{ edgeCount }}</strong><span>关系</span>
      </div>
    </header>

    <div class="graph-toolbar glass-panel">
      <label class="graph-search">
        <Search :size="16" />
        <input v-model="query" placeholder="搜索标题、条目名、标签" aria-label="搜索图谱" />
        <button v-if="query" type="button" aria-label="清除搜索" @click="query = ''"><X :size="14" /></button>
      </label>
      <button class="secondary-button" type="button" @click="load" :disabled="loading"><RefreshCw :size="15" :class="{ spin: loading }" /> 刷新</button>
      <button class="secondary-button" type="button" @click="resetView"><Maximize2 :size="15" /> 复位</button>
      <button class="secondary-button" type="button" :class="{ active: settingsOpen }" @click="settingsOpen = !settingsOpen"><Settings :size="15" /> 设置</button>
    </div>

    <div ref="surfaceRef" class="memory-graph-surface" aria-label="记忆关系图">
      <div ref="containerRef" class="sigma-container"></div>
      <div v-if="loading" class="memory-graph-empty"><span class="loading-spinner"></span><span>正在读取记忆关系…</span></div>
      <div v-else-if="error" class="memory-graph-empty"><span>{{ error }}</span><button class="secondary-button" type="button" @click="load">重试</button></div>
      <div v-else-if="!hasData" class="memory-graph-empty"><span>还没有记忆条目，先在记忆库新建一条。</span></div>

      <div v-if="tooltip" ref="tooltipRef" class="memory-graph-tooltip" :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }">
        <strong>{{ tooltip.title }}</strong>
        <span>{{ tooltip.type }} · {{ tooltip.connections }} 个连接</span>
        <span>标签：{{ tooltip.tags }}</span>
      </div>

      <aside v-if="settingsOpen" class="memory-graph-settings" aria-label="图谱设置">
        <h3>图谱设置</h3>
        <h4>Filters</h4>
        <div class="type-checks">
          <label v-for="(label, type) in typeLabels" :key="type"><input v-model="selectedTypes[type]" type="checkbox" /><span>{{ label }}</span></label>
        </div>
        <label><span>显示孤儿节点</span><input v-model="showOrphans" type="checkbox" /></label>
        <label><span>共同标签边</span><input v-model="includeTags" type="checkbox" /></label>
        <h4>Display</h4>
        <label><span>节点尺寸</span><input v-model.number="nodeScale" type="range" min="0.6" max="1.8" step="0.1" /></label>
        <label><span>标签阈值</span><input v-model.number="labelThreshold" type="range" min="2" max="18" step="1" /></label>
        <h4>Forces</h4>
        <label><span>中心力</span><input v-model.number="forces.center" type="range" min="0.1" max="4" step="0.1" @change="applyForceChange" /></label>
        <label><span>斥力</span><input v-model.number="forces.repel" type="range" min="20" max="220" step="10" @change="applyForceChange" /></label>
        <label><span>弹簧</span><input v-model.number="forces.link" type="range" min="0" max="2" step="0.1" @change="applyForceChange" /></label>
        <label><span>连接距离</span><input v-model.number="forces.distance" type="range" min="40" max="160" step="10" @change="applyForceChange" /></label>
      </aside>

      <div class="memory-graph-toolbar">
        <button class="icon-button" type="button" title="放大" aria-label="放大" @click="zoomIn">＋</button>
        <button class="icon-button" type="button" title="缩小" aria-label="缩小" @click="zoomOut">－</button>
        <button class="icon-button" type="button" title="筛选设置" aria-label="筛选设置" @click="settingsOpen = !settingsOpen"><Filter :size="16" /></button>
      </div>
      <div class="memory-graph-legend"><span><i class="user"></i>用户</span><span><i class="project"></i>项目</span><span><i class="reference"></i>参考</span><span><i class="feedback"></i>反馈</span></div>
    </div>
  </section>
</template>
