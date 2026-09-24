import Graph from 'graphology'
import FA2LayoutSync from 'graphology-layout-forceatlas2'
import FA2Layout from 'graphology-layout-forceatlas2/worker'
import Sigma from 'sigma'
import { drawDiscNodeLabel, NodeCircleProgram } from 'sigma/rendering'

const colors = { user: '#A78BFA', project: '#6EA8FE', reference: '#77C5D5', feedback: '#E3A85B' }
const typeLabels = { user: '用户', project: '项目', reference: '参考', feedback: '反馈' }
const programs = { user: NodeCircleProgram, project: NodeCircleProgram, reference: NodeCircleProgram, feedback: NodeCircleProgram }
const settingsKey = 'mshub.memoryGraph.settings.v1'
const motionKey = 'mshub.memoryGraph.motion.v1'
let bridge = null
let graph = null
let renderer = null
let layout = null
let hovered = null
let hoveredNeighbors = new Set()
let raw = { nodes: [], edges: [] }
let query = ''
let theme = { background: '#FFFFFF', label: '#000A1E', dimNode: '#E7E4DF', dimEdge: '#D7DEE8', focusEdge: '#B9C5D8' }
let paletteFromBridge = null
let graphSettings = {
  includeTags: false, showOrphans: true, labelThreshold: 8, nodeScale: 1,
  selectedTypes: { user: true, project: true, reference: true, feedback: true },
  forces: { center: 1, repel: 100, link: 1, distance: 80 },
}
let floatFrame = 0
let lastInteraction = 0
let interactionDepth = 0
let floatResumeTimer = null
let reduceMotion = false
// ---- v1.5.0 漂浮引擎：直写 graphology 坐标的显示层漂移 ----
// v1.4.2 的"闲置微动"在 nodeReducer 里加 0.015 单位偏移，但 sigma v3 的
// reducer 输出变化不会推进 WebGL 渲染缓冲，实际画面是静止的——这就是
// "死板"的根因。v1.5.0 改为 rAF 里直接 setNodeAttribute 写坐标：
// FA2 收敛后快照基准位（floatBase），每帧写 base + sin/cos 偏移，
// graphology 的 graph 事件驱动 sigma 增量渲染，真正上屏。
let floatBase = new Map()   // id -> {x, y} 基准坐标（FA2 收敛 / 拖拽结果）
let floatSeeds = new Map()  // id -> {phaseX, phaseY, periodX, periodY, amplitudePx}
let floatTime = 0
let floatLastTick = 0
let floatGraphPerPx = 1     // 图谱单位/屏幕像素，用于把幅度换算成恒定屏幕位移
window.mshubGraphReady = false

const $ = (selector) => document.querySelector(selector)
const surface = $('#surface')
const message = $('#message')
const tooltip = $('#tooltip')

function readSettings() { try { return JSON.parse(localStorage.getItem(settingsKey) || '{}') } catch { return {} } }
function mergeSettings(value) {
  const incoming = value && typeof value === 'object' ? value : {}
  return {
    ...graphSettings,
    ...incoming,
    selectedTypes: { ...graphSettings.selectedTypes, ...(incoming.selectedTypes || {}) },
    forces: { ...graphSettings.forces, ...(incoming.forces || {}) },
  }
}
function saveSettings() { try { localStorage.setItem(settingsKey, JSON.stringify(graphSettings)); bridge?.writeGraphSettings(JSON.stringify(graphSettings)) } catch {} }
function readMotionSetting() { try { return JSON.parse(localStorage.getItem(motionKey) || '{"enabled":true}').enabled !== false } catch { return true } }
function stableHash(value) { let hash = 2166136261; for (const char of String(value)) { hash ^= char.codePointAt(0); hash = Math.imul(hash, 16777619) } return hash >>> 0 }
function seededPosition(id, index) { return { x: ((stableHash(`${id}:x:${index}`) / 0xffffffff) * 2 - 1) * 18, y: ((stableHash(`${id}:y:${index}`) / 0xffffffff) * 2 - 1) * 18 } }
function parseColor(value) { const text = String(value || '').trim(); const hex = text.match(/^#([0-9a-f]{6})$/i); if (hex) return [parseInt(hex[1].slice(0,2),16), parseInt(hex[1].slice(2,4),16), parseInt(hex[1].slice(4,6),16)]; const rgb = text.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i); return rgb ? rgb.slice(1, 4).map(Number) : null }
function mix(fg, amount, bg) { const a = parseColor(fg) || [166,166,166]; const b = parseColor(bg) || [255,255,255]; const v = Math.max(0, Math.min(1, Number(amount) || 0)); return `#${a.map((x, i) => Math.round(x * v + b[i] * (1 - v)).toString(16).padStart(2,'0')).join('')}` }
function refreshTheme() { const bg = paletteFromBridge?.background || '#FFFFFF'; const label = paletteFromBridge?.label || '#000A1E'; theme = { background: bg, label, dimNode: mix('#A6A6A6', .1, bg), dimEdge: mix('#8C8C8C', .12, bg), focusEdge: mix('#8C8C8C', .45, bg) }; renderer?.setSetting('labelColor', { color: theme.label }); renderer?.refresh() }
function normalize(node, index) { const id = String(node.id || node.name || `memory-${index}`); const pos = seededPosition(id, index); const type = colors[node.type] ? node.type : 'reference'; return { id, label: String(node.title || id), title: String(node.title || id), type, source: String(node.source || ''), tags: Array.isArray(node.tags) ? node.tags : [], x: Number.isFinite(node.x) ? node.x : pos.x, y: Number.isFinite(node.y) ? node.y : pos.y, baseX: Number.isFinite(node.x) ? node.x : pos.x, baseY: Number.isFinite(node.y) ? node.y : pos.y, phase: stableHash(`${id}:float`) % 6283 / 1000, color: colors[type] } }
function nodeMatch(data) { const q = query.trim().toLocaleLowerCase(); if (!q) return true; return [data.id, data.title, data.source, ...(data.tags || [])].some((value) => String(value || '').toLocaleLowerCase().includes(q)) }
// v1.5.0：reducer 不再掺漂浮偏移（sigma v3 的 reducer 输出不进 WebGL 缓冲），
// 漂浮由 floatTick 直接写 graphology 坐标实现，reducer 只管渲染态。
function nodeReducer(node, data) { const focused = !hovered || node === hovered || hoveredNeighbors.has(node); const match = nodeMatch(data); const dimmed = !focused || !match; const degree = graph?.degree(node) || 0; return { ...data, size: (4 + Math.sqrt(degree) * 2) * Number(graphSettings.nodeScale || 1), color: dimmed ? theme.dimNode : data.color, label: dimmed ? null : data.label, forceLabel: node === hovered } }
function edgeReducer(edge, data) { const [source, target] = graph.extremities(edge); const linked = hovered && (source === hovered || target === hovered); const color = linked ? mix(graph.getNodeAttributes(hovered)?.color || '#A6A6A6', .6, theme.background) : (hovered ? theme.dimEdge : (data.kind === '共同标签' ? mix('#B4B4B4', .3, theme.background) : theme.focusEdge)); return { ...data, color, size: linked ? 1.6 : 1 } }
function drawLabel(context, data, settings) { if (!data.label) return; context.save(); context.font = `${settings.labelWeight} ${settings.labelSize}px ${settings.labelFont}`; context.lineJoin = 'round'; context.lineWidth = 4; context.strokeStyle = theme.background; context.strokeText(data.label, data.x + data.size + 3, data.y + settings.labelSize / 3); drawDiscNodeLabel(context, data, settings); context.restore() }
function edgeKey(source, target, kind) { const pair = [source, target].sort(); return `${kind}:${pair[0]}::${pair[1]}` }
function syncGraph(data) { graph = new Graph({ type: 'undirected', multi: true }); const selected = graphSettings.selectedTypes || {}; data.nodes.filter((node) => selected[node.type] !== false).forEach((node, index) => { const item = normalize(node, index); graph.addNode(item.id, item) }); const distance = Number(graphSettings.forces?.distance || 80); const distanceMultiplier = 2 - (distance / 160) * 1.5; data.edges.forEach((edge) => { const source = String(edge.source); const target = String(edge.target); if (!graph.hasNode(source) || !graph.hasNode(target) || source === target) return; const kind = edge.kind || '双链'; const key = edgeKey(source, target, kind); if (!graph.hasEdge(key)) { const baseWeight = kind === '共同标签' ? .5 : 2; graph.addEdgeWithKey(key, source, target, { kind, baseWeight, weight: baseWeight * distanceMultiplier, size: 1 }) } }); if (graphSettings.showOrphans === false) graph.forEachNode((id) => { if (graph.degree(id) === 0) graph.dropNode(id) }) }
function applyForceSettings() { if (!graph) return; const distance = Number(graphSettings.forces?.distance || 80); const distanceMultiplier = 2 - (distance / 160) * 1.5; graph.forEachEdge((edge) => { const data = graph.getEdgeAttributes(edge); graph.setEdgeAttribute(edge, 'weight', Number(data.baseWeight || data.weight || 1) * distanceMultiplier) }) }
function layoutSettings() { return { gravity: 1, scalingRatio: 100, slowDown: 1, barnesHutOptimize: true, barnesHutTheta: .5, edgeWeightInfluence: 1, adjustSizes: true } }
// v1.5.0：斥力映射 ×0.14。旧版直接把 forces.repel（默认 100）塞给 scalingRatio，
// 对 58 节点的小图过强，节点被推得极散、群落感尽失。0.14 是实测系数，
// 对应 repel=100 → scalingRatio≈14，群落聚拢且边可见。
function repelToScaling(repel) { return Number(repel || 100) * 0.14 }
function startLayout() {
  stopFloat(); floatBase.clear()  // 布局期间坐标归 FA2 所有，漂浮让位
  layout?.kill?.(); layout = null
  if (!graph || graph.order < 2) { snapshotFloatBase(); syncFloat(); return }
  // graphology-layout-forceatlas2/worker creates a Blob URL in the package
  // itself.  Chromium can still reject Blob workers for a locked-down local
  // file/qrc origin, so use a bounded synchronous pass as the deterministic
  // fallback instead of introducing a localhost server.
  const force = graphSettings.forces || {}
  if (location.protocol === 'file:' || location.protocol === 'qrc:') {
    const iterations = graph.order > 1800 ? 18 : graph.order > 800 ? 30 : 54
    FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: repelToScaling(force.repel), edgeWeightInfluence: Number(force.link || 1) } })
    renderer?.refresh()
    snapshotFloatBase(); syncFloat()
    return
  }
  try {
    layout = new FA2Layout(graph, { settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: repelToScaling(force.repel), edgeWeightInfluence: Number(force.link || 1) } })
    layout.start()
    window.setTimeout(() => { layout?.stop(); layout = null; snapshotFloatBase(); syncFloat() }, graph.order > 1800 ? 2600 : 1800)
  } catch (error) {
    console.warn('FA2 worker unavailable; using synchronous fallback', error)
    const iterations = graph.order > 1800 ? 18 : graph.order > 800 ? 30 : 54
    FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: repelToScaling(force.repel), edgeWeightInfluence: Number(force.link || 1) } })
    renderer?.refresh()
    snapshotFloatBase(); syncFloat()
  }
}
function reheatAfterDrag() {
  if (layout || !graph || graph.order < 2) return
  const iterations = graph.order > 1800 ? 4 : graph.order > 800 ? 7 : 12
  FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), slowDown: 2, scalingRatio: repelToScaling(graphSettings.forces?.repel) } })
  renderer?.refresh()
  snapshotFloatBase(); syncFloat()
}
function showTooltip(node, event) { const data = graph.getNodeAttributes(node); tooltip.innerHTML = ''; const title = document.createElement('strong'); title.textContent = data.title; const meta = document.createElement('span'); meta.textContent = `${typeLabels[data.type] || data.type} · ${graph.degree(node)} 个连接`; const tags = document.createElement('span'); tags.textContent = `标签：${data.tags?.join('、') || '无标签'}`; tooltip.append(title, meta, tags); tooltip.hidden = false; const rect = surface.getBoundingClientRect(); tooltip.style.left = `${Math.min(rect.width - tooltip.offsetWidth - 16, Math.max(16, event.x + 12))}px`; tooltip.style.top = `${Math.min(rect.height - tooltip.offsetHeight - 16, Math.max(16, event.y + 12))}px` }
function clearHover() { hovered = null; hoveredNeighbors = new Set(); tooltip.hidden = true; renderer?.refresh() }
function bindRenderer() { renderer.on('enterNode', ({ node, event }) => { hovered = node; hoveredNeighbors = new Set([node, ...graph.neighbors(node)]); showTooltip(node, event); renderer.refresh() }); renderer.on('leaveNode', clearHover); renderer.on('clickNode', ({ node }) => bridge?.openMemory(node)); renderer.on('clickStage', clearHover); renderer.on('doubleClickStage', () => renderer.getCamera().animatedReset({ duration: 300 })); renderer.on('downNode', ({ node, event }) => { pauseFloat(); renderer.getCamera().disable(); event.preventSigmaDefault(); event.original.preventDefault(); layout?.start(); renderer.getMouseCaptor().on('mousemovebody', moveNode); renderer.getMouseCaptor().once('mouseup', () => { renderer.getCamera().enable(); renderer.getMouseCaptor().removeListener('mousemovebody', moveNode); if (layout) window.setTimeout(() => { layout?.stop(); layout = null; snapshotFloatBase(); syncFloat() }, 1800); else reheatAfterDrag(); resumeFloat() }); function moveNode(mouseEvent) { const position = renderer.viewportToGraph(mouseEvent); graph.setNodeAttribute(node, 'x', position.x); graph.setNodeAttribute(node, 'y', position.y); graph.setNodeAttribute(node, 'baseX', position.x); graph.setNodeAttribute(node, 'baseY', position.y); floatBase.set(node, { x: position.x, y: position.y }); renderer.refresh() } }); renderer.getMouseCaptor().on('mousedown', pauseFloat); renderer.getMouseCaptor().on('mouseup', resumeFloat); renderer.getMouseCaptor().on('wheel', pauseFloat) }
function render(data) { raw = data; syncGraph(data); $('#node-count').textContent = String(graph.order); $('#edge-count').textContent = String(graph.size); message.classList.toggle('hidden', graph.order > 0); refreshTheme(); if (!renderer) { renderer = new Sigma(graph, $('#sigma-container'), { renderLabels: true, labelRenderedSizeThreshold: Number(graphSettings.labelThreshold || 8), labelFont: 'Segoe UI, Microsoft YaHei, sans-serif', labelSize: 12, labelWeight: '500', labelColor: { color: theme.label }, defaultNodeColor: '#A6A6A6', defaultEdgeColor: theme.focusEdge, defaultNodeType: 'circle', nodeProgramClasses: programs, defaultDrawNodeLabel: drawLabel, nodeReducer, edgeReducer, hideEdgesOnMove: graph.size > 8000, stagePadding: 28, zIndex: true }); bindRenderer() } else renderer.setGraph(graph); startLayout(); window.mshubGraphReady = true; window.mshubGraphNodeCount = graph.order; window.mshubGraphEdgeCount = graph.size }
function load() { if (!bridge) return; message.textContent = '正在读取记忆关系…'; message.classList.remove('hidden'); const kinds = $('#include-tags').checked ? 'link,tag' : 'link'; bridge.getGraph(kinds, (payload) => { try { render(JSON.parse(payload)) } catch (error) { message.textContent = `图谱数据解析失败：${error}` } }) }
window.mshubSetTheme = (mode) => { const value = mode === 'dark' ? 'dark' : 'light'; document.documentElement.dataset.theme = value; document.body.dataset.theme = value; refreshTheme() }
window.mshubSetPalette = (payload) => { try { paletteFromBridge = typeof payload === 'string' ? JSON.parse(payload) : payload; window.mshubSetTheme(paletteFromBridge.theme); } catch {} }
window.mshubSetGraphSettings = (payload) => { try { graphSettings = mergeSettings(typeof payload === 'string' ? JSON.parse(payload) : payload); saveSettings(); load() } catch {} }
// ---- v1.5.0 漂浮引擎 ----------------------------------------------------
// 每节点按 id 播种：相位错开、周期 3.6~7s、屏幕幅度 2.6~4.6px。
// 基准位 = FA2 收敛/拖拽后的 graphology 坐标（floatBase 快照）；每帧写
// base + sin/cos 偏移。只改显示层坐标，不回写 baseX/baseY（那是 FA2 的
// 语义位，reheat 仍从真实位置出发）。
function floatSeedFor(nodeId) {
  let seed = floatSeeds.get(nodeId)
  if (!seed) {
    const h1 = stableHash(`${nodeId}:x`)
    const h2 = stableHash(`${nodeId}:y`)
    const h3 = stableHash(`${nodeId}:a`)
    seed = {
      phaseX: (h1 % 6283) / 1000,
      phaseY: (h2 % 6283) / 1000,
      periodX: 3600 + (h1 % 3000),
      periodY: 4100 + ((h2 >>> 8) % 2900),
      amplitudePx: 2.6 + (h3 % 100) / 100 * 2.0,
    }
    floatSeeds.set(nodeId, seed)
  }
  return seed
}
function snapshotFloatBase() {
  if (!graph) return
  floatBase.clear()
  graph.forEachNode((id, attrs) => { floatBase.set(id, { x: attrs.x, y: attrs.y }) })
}
function updateFloatScale() {
  // 用 viewportToGraph 实测当前缩放下的 图谱单位/像素 比，
  // 让漂浮幅度在任何缩放级别下都保持恒定的屏幕位移。
  if (!renderer) return
  try {
    const a = renderer.viewportToGraph({ x: 0, y: 0 })
    const b = renderer.viewportToGraph({ x: 100, y: 0 })
    const perPx = Math.abs(b.x - a.x) / 100
    if (Number.isFinite(perPx) && perPx > 0) floatGraphPerPx = perPx
  } catch {}
}
function applyFloatFrame() {
  if (!graph) return
  const amplitude = floatGraphPerPx
  graph.forEachNode((id, attrs) => {
    const base = floatBase.get(id) || attrs
    const seed = floatSeedFor(id)
    const x = base.x + Math.sin(floatTime / seed.periodX + seed.phaseX) * seed.amplitudePx * amplitude
    const y = base.y + Math.cos(floatTime / seed.periodY + seed.phaseY) * seed.amplitudePx * amplitude
    graph.setNodeAttribute(id, 'x', x)
    graph.setNodeAttribute(id, 'y', y)
  })
}
function floatTick(now) {
  floatFrame = requestAnimationFrame(floatTick)
  if (interactionDepth || now - lastInteraction < 1000 || !graph || !renderer) return
  // 拖拽/平移/缩放时 sigma 自己会触发渲染；静止期由这里驱动增量渲染。
  if (!floatLastTick) floatLastTick = now
  floatTime += Math.min(64, now - floatLastTick)  // 帧率波动时步长封顶，漂浮不跳变
  floatLastTick = now
  applyFloatFrame()
}
function syncFloat() {
  const enabled = graph && graph.order <= 3000 && graph.size <= 8000 && !reduceMotion && readMotionSetting()
  if (enabled && !floatFrame) { floatLastTick = 0; updateFloatScale(); floatFrame = requestAnimationFrame(floatTick) }
  if (!enabled && floatFrame) stopFloat()
}
function stopFloat() { if (floatFrame) { cancelAnimationFrame(floatFrame); floatFrame = 0 }; floatLastTick = 0 }
function pauseFloat() { interactionDepth += 1; lastInteraction = performance.now(); if (floatResumeTimer) clearTimeout(floatResumeTimer); floatResumeTimer = setTimeout(() => { interactionDepth = Math.max(0, interactionDepth - 1); }, 140) }
function resumeFloat() { interactionDepth = Math.max(0, interactionDepth - 1); lastInteraction = performance.now(); updateFloatScale() }
window.mshubReloadGraph = () => load()
// v1.5.0 诊断接口：smoke-float 用它分辨"数据没到页面"与"渲染为 0"。
window.mshubDiagCount = () => JSON.stringify({ rawNodes: raw.nodes.length, rawEdges: raw.edges.length, graphOrder: graph?.order ?? -1, graphSize: graph?.size ?? -1, driftTime: Math.round(floatTime), floatBaseSize: floatBase.size })
window.mshubDiagBridge = (cb) => { try { bridge?.getGraph('link', (p) => { try { const d = JSON.parse(p); cb(JSON.stringify({ payloadNodes: d.nodes?.length ?? -1, payloadLen: p.length })) } catch (e) { cb('parse-err:' + e) } }) } catch (e) { cb('call-err:' + e) } }
$('#query').addEventListener('input', (event) => { query = event.target.value; renderer?.refresh() })
$('#clear').addEventListener('click', () => { $('#query').value = ''; query = ''; renderer?.refresh() })
$('#refresh').addEventListener('click', load)
$('#reset').addEventListener('click', () => renderer?.getCamera().animatedReset({ duration: 300 }))
$('#zoom-in').addEventListener('click', () => renderer?.getCamera().animatedZoom({ factor: .75, duration: 220 }))
$('#zoom-out').addEventListener('click', () => renderer?.getCamera().animatedUnzoom({ factor: .75, duration: 220 }))
graphSettings = mergeSettings(readSettings())
reduceMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
$('#include-tags').checked = Boolean(graphSettings.includeTags)
$('#include-tags').addEventListener('change', () => { graphSettings.includeTags = $('#include-tags').checked; saveSettings(); load() })
window.matchMedia?.('(prefers-reduced-motion: reduce)').addEventListener?.('change', (event) => { reduceMotion = event.matches; if (reduceMotion) stopFloat(); else syncFloat() })
if (window.QWebChannel && window.qt?.webChannelTransport) new QWebChannel(window.qt.webChannelTransport, (channel) => { bridge = channel.objects.mshub; bridge.getPalette((payload) => { try { window.mshubSetPalette(payload); } catch {} }); bridge.readGraphSettings((payload) => { try { graphSettings = mergeSettings(JSON.parse(payload)); $('#include-tags').checked = Boolean(graphSettings.includeTags); syncSettingsPanel(); } catch {} }); load() })
else { message.textContent = '图谱桥接未就绪（请从 Qt WebEngine 打开）。' }

function bindSettingsPanel() {
  const panel = $('#graph-settings'); const toggle = $('#settings-toggle');
  toggle.addEventListener('click', () => { panel.hidden = !panel.hidden; toggle.setAttribute('aria-expanded', String(!panel.hidden)) })
  const types = panel.querySelectorAll('[data-type]'); types.forEach((input) => input.addEventListener('change', () => { graphSettings.selectedTypes[input.dataset.type] = input.checked; saveSettings(); load() }))
  const orphan = $('#show-orphans'); orphan.addEventListener('change', () => { graphSettings.showOrphans = orphan.checked; saveSettings(); load() })
  const motion = $('#motion-toggle'); motion.checked = readMotionSetting(); motion.addEventListener('change', () => { localStorage.setItem(motionKey, JSON.stringify({ enabled: motion.checked })); if (!motion.checked) stopFloat(); else { snapshotFloatBase(); syncFloat() } })
  panel.querySelectorAll('[data-setting]').forEach((input) => input.addEventListener('input', () => { const [group, key] = input.dataset.setting.split('.'); if (group === 'forces') graphSettings.forces[key] = Number(input.value); else graphSettings[key] = Number(input.value); input.nextElementSibling.textContent = input.value; saveSettings(); if (group === 'forces') { applyForceSettings(); startLayout(); } if (key === 'labelThreshold') renderer?.setSetting('labelRenderedSizeThreshold', Number(input.value)); renderer?.refresh() }))
  syncSettingsPanel()
}
function syncSettingsPanel() { const panel = $('#graph-settings'); if (!panel) return; panel.querySelectorAll('[data-setting]').forEach((input) => { const [group, key] = input.dataset.setting.split('.'); input.value = group === 'forces' ? graphSettings.forces[key] : graphSettings[key]; input.nextElementSibling.textContent = input.value }); panel.querySelectorAll('[data-type]').forEach((input) => { input.checked = graphSettings.selectedTypes[input.dataset.type] !== false }); $('#show-orphans').checked = graphSettings.showOrphans !== false; $('#motion-toggle').checked = readMotionSetting() }
bindSettingsPanel()
