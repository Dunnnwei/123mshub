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
function seededPosition(id, index) { return { x: ((stableHash(`${id}:x:${index}`) / 0xffffffff) * 2 - 1) * 4, y: ((stableHash(`${id}:y:${index}`) / 0xffffffff) * 2 - 1) * 4 } }
function parseColor(value) { const text = String(value || '').trim(); const hex = text.match(/^#([0-9a-f]{6})$/i); if (hex) return [parseInt(hex[1].slice(0,2),16), parseInt(hex[1].slice(2,4),16), parseInt(hex[1].slice(4,6),16)]; const rgb = text.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i); return rgb ? rgb.slice(1, 4).map(Number) : null }
function mix(fg, amount, bg) { const a = parseColor(fg) || [166,166,166]; const b = parseColor(bg) || [255,255,255]; const v = Math.max(0, Math.min(1, Number(amount) || 0)); return `#${a.map((x, i) => Math.round(x * v + b[i] * (1 - v)).toString(16).padStart(2,'0')).join('')}` }
function refreshTheme() { const bg = paletteFromBridge?.background || '#FFFFFF'; const label = paletteFromBridge?.label || '#000A1E'; theme = { background: bg, label, dimNode: mix('#A6A6A6', .1, bg), dimEdge: mix('#8C8C8C', .12, bg), focusEdge: mix('#8C8C8C', .45, bg) }; renderer?.setSetting('labelColor', { color: theme.label }); renderer?.refresh() }
function normalize(node, index) { const id = String(node.id || node.name || `memory-${index}`); const pos = seededPosition(id, index); const type = colors[node.type] ? node.type : 'reference'; return { id, label: String(node.title || id), title: String(node.title || id), type, source: String(node.source || ''), tags: Array.isArray(node.tags) ? node.tags : [], x: Number.isFinite(node.x) ? node.x : pos.x, y: Number.isFinite(node.y) ? node.y : pos.y, baseX: Number.isFinite(node.x) ? node.x : pos.x, baseY: Number.isFinite(node.y) ? node.y : pos.y, phase: stableHash(`${id}:float`) % 6283 / 1000, color: colors[type] } }
function nodeMatch(data) { const q = query.trim().toLocaleLowerCase(); if (!q) return true; return [data.id, data.title, data.source, ...(data.tags || [])].some((value) => String(value || '').toLocaleLowerCase().includes(q)) }
function nodeReducer(node, data) { const focused = !hovered || node === hovered || hoveredNeighbors.has(node); const match = nodeMatch(data); const dimmed = !focused || !match; const degree = graph?.degree(node) || 0; const offset = interactionDepth || reduceMotion ? { x: 0, y: 0 } : { x: Math.sin(performance.now() / 600 + data.phase) * 0.015, y: Math.cos(performance.now() / 800 + data.phase) * 0.015 }; return { ...data, x: data.x + offset.x, y: data.y + offset.y, size: (4 + Math.sqrt(degree) * 2) * Number(graphSettings.nodeScale || 1), color: dimmed ? theme.dimNode : data.color, label: dimmed ? null : data.label, forceLabel: node === hovered } }
function edgeReducer(edge, data) { const [source, target] = graph.extremities(edge); const linked = hovered && (source === hovered || target === hovered); const color = linked ? mix(graph.getNodeAttributes(hovered)?.color || '#A6A6A6', .6, theme.background) : (hovered ? theme.dimEdge : (data.kind === '共同标签' ? mix('#B4B4B4', .3, theme.background) : theme.focusEdge)); return { ...data, color, size: linked ? 1.6 : 1 } }
function drawLabel(context, data, settings) { if (!data.label) return; context.save(); context.font = `${settings.labelWeight} ${settings.labelSize}px ${settings.labelFont}`; context.lineJoin = 'round'; context.lineWidth = 4; context.strokeStyle = theme.background; context.strokeText(data.label, data.x + data.size + 3, data.y + settings.labelSize / 3); drawDiscNodeLabel(context, data, settings); context.restore() }
function edgeKey(source, target, kind) { const pair = [source, target].sort(); return `${kind}:${pair[0]}::${pair[1]}` }
function syncGraph(data) { graph = new Graph({ type: 'undirected', multi: true }); const selected = graphSettings.selectedTypes || {}; data.nodes.filter((node) => selected[node.type] !== false).forEach((node, index) => { const item = normalize(node, index); graph.addNode(item.id, item) }); const distance = Number(graphSettings.forces?.distance || 80); const distanceMultiplier = 2 - (distance / 160) * 1.5; data.edges.forEach((edge) => { const source = String(edge.source); const target = String(edge.target); if (!graph.hasNode(source) || !graph.hasNode(target) || source === target) return; const kind = edge.kind || '双链'; const key = edgeKey(source, target, kind); if (!graph.hasEdge(key)) { const baseWeight = kind === '共同标签' ? .5 : 2; graph.addEdgeWithKey(key, source, target, { kind, baseWeight, weight: baseWeight * distanceMultiplier, size: 1 }) } }); if (graphSettings.showOrphans === false) graph.forEachNode((id) => { if (graph.degree(id) === 0) graph.dropNode(id) }) }
function applyForceSettings() { if (!graph) return; const distance = Number(graphSettings.forces?.distance || 80); const distanceMultiplier = 2 - (distance / 160) * 1.5; graph.forEachEdge((edge) => { const data = graph.getEdgeAttributes(edge); graph.setEdgeAttribute(edge, 'weight', Number(data.baseWeight || data.weight || 1) * distanceMultiplier) }) }
function layoutSettings() { return { gravity: 1, scalingRatio: 100, slowDown: 1, barnesHutOptimize: true, barnesHutTheta: .5, edgeWeightInfluence: 1, adjustSizes: true } }
function startLayout() {
  layout?.kill?.(); layout = null
  if (!graph || graph.order < 2) return
  // graphology-layout-forceatlas2/worker creates a Blob URL in the package
  // itself.  Chromium can still reject Blob workers for a locked-down local
  // file/qrc origin, so use a bounded synchronous pass as the deterministic
  // fallback instead of introducing a localhost server.
  const force = graphSettings.forces || {}
  if (location.protocol === 'file:' || location.protocol === 'qrc:') {
    const iterations = graph.order > 1800 ? 18 : graph.order > 800 ? 30 : 54
    FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: Number(force.repel || 100), edgeWeightInfluence: Number(force.link || 1) } })
    renderer?.refresh()
    return
  }
  try {
    layout = new FA2Layout(graph, { settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: Number(force.repel || 100), edgeWeightInfluence: Number(force.link || 1) } })
    layout.start()
    window.setTimeout(() => layout?.stop(), graph.order > 1800 ? 2600 : 1800)
  } catch (error) {
    console.warn('FA2 worker unavailable; using synchronous fallback', error)
    const iterations = graph.order > 1800 ? 18 : graph.order > 800 ? 30 : 54
    FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), gravity: Number(force.center || 1), scalingRatio: Number(force.repel || 100), edgeWeightInfluence: Number(force.link || 1) } })
    renderer?.refresh()
  }
}
function reheatAfterDrag() {
  if (layout || !graph || graph.order < 2) return
  const iterations = graph.order > 1800 ? 4 : graph.order > 800 ? 7 : 12
  FA2LayoutSync.assign(graph, { iterations, settings: { ...layoutSettings(), slowDown: 2 } })
  renderer?.refresh()
}
function showTooltip(node, event) { const data = graph.getNodeAttributes(node); tooltip.innerHTML = ''; const title = document.createElement('strong'); title.textContent = data.title; const meta = document.createElement('span'); meta.textContent = `${typeLabels[data.type] || data.type} · ${graph.degree(node)} 个连接`; const tags = document.createElement('span'); tags.textContent = `标签：${data.tags?.join('、') || '无标签'}`; tooltip.append(title, meta, tags); tooltip.hidden = false; const rect = surface.getBoundingClientRect(); tooltip.style.left = `${Math.min(rect.width - tooltip.offsetWidth - 16, Math.max(16, event.x + 12))}px`; tooltip.style.top = `${Math.min(rect.height - tooltip.offsetHeight - 16, Math.max(16, event.y + 12))}px` }
function clearHover() { hovered = null; hoveredNeighbors = new Set(); tooltip.hidden = true; renderer?.refresh() }
function bindRenderer() { renderer.on('enterNode', ({ node, event }) => { hovered = node; hoveredNeighbors = new Set([node, ...graph.neighbors(node)]); showTooltip(node, event); renderer.refresh() }); renderer.on('leaveNode', clearHover); renderer.on('clickNode', ({ node }) => bridge?.openMemory(node)); renderer.on('clickStage', clearHover); renderer.on('doubleClickStage', () => renderer.getCamera().animatedReset({ duration: 300 })); renderer.on('downNode', ({ node, event }) => { pauseFloat(); renderer.getCamera().disable(); event.preventSigmaDefault(); event.original.preventDefault(); layout?.start(); renderer.getMouseCaptor().on('mousemovebody', moveNode); renderer.getMouseCaptor().once('mouseup', () => { renderer.getCamera().enable(); renderer.getMouseCaptor().removeListener('mousemovebody', moveNode); if (layout) window.setTimeout(() => layout?.stop(), 1800); else reheatAfterDrag(); resumeFloat() }); function moveNode(mouseEvent) { const position = renderer.viewportToGraph(mouseEvent); graph.setNodeAttribute(node, 'x', position.x); graph.setNodeAttribute(node, 'y', position.y); graph.setNodeAttribute(node, 'baseX', position.x); graph.setNodeAttribute(node, 'baseY', position.y); renderer.refresh() } }); renderer.getMouseCaptor().on('mousedown', pauseFloat); renderer.getMouseCaptor().on('mouseup', resumeFloat); renderer.getMouseCaptor().on('wheel', pauseFloat) }
function render(data) { raw = data; syncGraph(data); $('#node-count').textContent = String(graph.order); $('#edge-count').textContent = String(graph.size); message.classList.toggle('hidden', graph.order > 0); refreshTheme(); if (!renderer) { renderer = new Sigma(graph, $('#sigma-container'), { renderLabels: true, labelRenderedSizeThreshold: Number(graphSettings.labelThreshold || 8), labelFont: 'Segoe UI, Microsoft YaHei, sans-serif', labelSize: 12, labelWeight: '500', labelColor: { color: theme.label }, defaultNodeColor: '#A6A6A6', defaultEdgeColor: theme.focusEdge, defaultNodeType: 'circle', nodeProgramClasses: programs, defaultDrawNodeLabel: drawLabel, nodeReducer, edgeReducer, hideEdgesOnMove: graph.size > 8000, stagePadding: 28, zIndex: true }); bindRenderer() } else renderer.setGraph(graph); startLayout(); const shouldFloat = graph.order <= 3000 && graph.size <= 8000 && !reduceMotion && readMotionSetting(); if (shouldFloat) startFloat(); else if (floatFrame) { cancelAnimationFrame(floatFrame); floatFrame = 0; } window.mshubGraphReady = true; window.mshubGraphNodeCount = graph.order; window.mshubGraphEdgeCount = graph.size }
function load() { if (!bridge) return; message.textContent = '正在读取记忆关系…'; message.classList.remove('hidden'); const kinds = $('#include-tags').checked ? 'link,tag' : 'link'; bridge.getGraph(kinds, (payload) => { try { render(JSON.parse(payload)) } catch (error) { message.textContent = `图谱数据解析失败：${error}` } }) }
window.mshubSetTheme = (mode) => { const value = mode === 'dark' ? 'dark' : 'light'; document.documentElement.dataset.theme = value; document.body.dataset.theme = value; refreshTheme() }
window.mshubSetPalette = (payload) => { try { paletteFromBridge = typeof payload === 'string' ? JSON.parse(payload) : payload; window.mshubSetTheme(paletteFromBridge.theme); } catch {} }
window.mshubSetGraphSettings = (payload) => { try { graphSettings = mergeSettings(typeof payload === 'string' ? JSON.parse(payload) : payload); saveSettings(); load() } catch {} }
function startFloat() { if (floatFrame || !graph || graph.order > 3000 || graph.size > 8000) return; const tick = (now) => { floatFrame = requestAnimationFrame(tick); if (interactionDepth || now - lastInteraction < 1000 || !graph || !renderer) return; renderer.refresh() }; floatFrame = requestAnimationFrame(tick) }
function pauseFloat() { interactionDepth += 1; lastInteraction = performance.now(); if (floatResumeTimer) clearTimeout(floatResumeTimer); floatResumeTimer = setTimeout(() => { interactionDepth = Math.max(0, interactionDepth - 1); }, 140) }
function resumeFloat() { interactionDepth = Math.max(0, interactionDepth - 1); lastInteraction = performance.now() }
window.mshubReloadGraph = () => load()
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
window.matchMedia?.('(prefers-reduced-motion: reduce)').addEventListener?.('change', (event) => { reduceMotion = event.matches; if (reduceMotion && floatFrame) cancelAnimationFrame(floatFrame); floatFrame = 0; if (!reduceMotion) startFloat() })
if (window.QWebChannel && window.qt?.webChannelTransport) new QWebChannel(window.qt.webChannelTransport, (channel) => { bridge = channel.objects.mshub; bridge.getPalette((payload) => { try { window.mshubSetPalette(payload); } catch {} }); bridge.readGraphSettings((payload) => { try { graphSettings = mergeSettings(JSON.parse(payload)); $('#include-tags').checked = Boolean(graphSettings.includeTags); syncSettingsPanel(); } catch {} }); load() })
else { message.textContent = '图谱桥接未就绪（请从 Qt WebEngine 打开）。' }

function bindSettingsPanel() {
  const panel = $('#graph-settings'); const toggle = $('#settings-toggle');
  toggle.addEventListener('click', () => { panel.hidden = !panel.hidden; toggle.setAttribute('aria-expanded', String(!panel.hidden)) })
  const types = panel.querySelectorAll('[data-type]'); types.forEach((input) => input.addEventListener('change', () => { graphSettings.selectedTypes[input.dataset.type] = input.checked; saveSettings(); load() }))
  const orphan = $('#show-orphans'); orphan.addEventListener('change', () => { graphSettings.showOrphans = orphan.checked; saveSettings(); load() })
  const motion = $('#motion-toggle'); motion.checked = readMotionSetting(); motion.addEventListener('change', () => { localStorage.setItem(motionKey, JSON.stringify({ enabled: motion.checked })); if (!motion.checked && floatFrame) { cancelAnimationFrame(floatFrame); floatFrame = 0; } else startFloat() })
  panel.querySelectorAll('[data-setting]').forEach((input) => input.addEventListener('input', () => { const [group, key] = input.dataset.setting.split('.'); if (group === 'forces') graphSettings.forces[key] = Number(input.value); else graphSettings[key] = Number(input.value); input.nextElementSibling.textContent = input.value; saveSettings(); if (group === 'forces') { applyForceSettings(); startLayout(); } if (key === 'labelThreshold') renderer?.setSetting('labelRenderedSizeThreshold', Number(input.value)); renderer?.refresh() }))
  syncSettingsPanel()
}
function syncSettingsPanel() { const panel = $('#graph-settings'); if (!panel) return; panel.querySelectorAll('[data-setting]').forEach((input) => { const [group, key] = input.dataset.setting.split('.'); input.value = group === 'forces' ? graphSettings.forces[key] : graphSettings[key]; input.nextElementSibling.textContent = input.value }); panel.querySelectorAll('[data-type]').forEach((input) => { input.checked = graphSettings.selectedTypes[input.dataset.type] !== false }); $('#show-orphans').checked = graphSettings.showOrphans !== false; $('#motion-toggle').checked = readMotionSetting() }
bindSettingsPanel()
