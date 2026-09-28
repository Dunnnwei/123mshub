import Graph from 'graphology'
import FA2LayoutSync from 'graphology-layout-forceatlas2'
import FA2Layout from 'graphology-layout-forceatlas2/worker'
import Sigma from 'sigma'
import { drawDiscNodeLabel, NodeCircleProgram } from 'sigma/rendering'

const colors = { user: '#7144B8', project: '#0148D2', reference: '#006F72', feedback: '#97500A' }
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
let theme = { background: '#FFFFFF', label: '#171B23', dimNode: '#F3F5F8', dimEdge: '#E2E6EE', focusEdge: '#C1C9D7' }
let paletteFromBridge = null
// v1.7.3：默认值提为常量，"恢复默认"按钮直接引用（mergeSettings 的基底也换成它，
// 否则用当前值当基底会把已改的设置"固化"进恢复结果）
const DEFAULT_GRAPH_SETTINGS = {
  includeTags: false, showOrphans: true, labelThreshold: 8, nodeScale: 1,
  selectedTypes: { user: true, project: true, reference: true, feedback: true },
  forces: { center: 1, repel: 100, link: 1, distance: 80 },
}
let graphSettings = DEFAULT_GRAPH_SETTINGS
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
window.mshubDiagRender = () => {
  const canvas = document.querySelector('#sigma-container canvas')
  const first = graph?.nodes?.()[0]
  const node = first && graph ? graph.getNodeAttributes(first) : null
  const rect = $('#sigma-container')?.getBoundingClientRect()
  let camera = null
  try { camera = renderer?.getCamera()?.getState?.() || null } catch {}
  return JSON.stringify({
    canvas: canvas ? { width: canvas.width, height: canvas.height, cssWidth: canvas.clientWidth, cssHeight: canvas.clientHeight } : null,
    rect: rect ? { width: rect.width, height: rect.height } : null,
    first: first || null,
    node: node ? { x: node.x, y: node.y, size: node.size, color: node.color } : null,
    camera,
  })
}

const $ = (selector) => document.querySelector(selector)
const surface = $('#surface')
const message = $('#message')
const tooltip = $('#tooltip')
const nodeBrowser = $('#node-browser')
const nodeList = $('#node-list')
const openNode = $('#open-node')

function readSettings() { try { return JSON.parse(localStorage.getItem(settingsKey) || '{}') } catch { return {} } }
function mergeSettings(value) {
  const incoming = value && typeof value === 'object' ? value : {}
  return {
    ...DEFAULT_GRAPH_SETTINGS,
    ...incoming,
    selectedTypes: { ...DEFAULT_GRAPH_SETTINGS.selectedTypes, ...(incoming.selectedTypes || {}) },
    forces: { ...DEFAULT_GRAPH_SETTINGS.forces, ...(incoming.forces || {}) },
  }
}
function saveSettings() { try { localStorage.setItem(settingsKey, JSON.stringify(graphSettings)); bridge?.writeGraphSettings(JSON.stringify(graphSettings)) } catch {} }
function readMotionSetting() { try { return JSON.parse(localStorage.getItem(motionKey) || '{"enabled":true}').enabled !== false } catch { return true } }
function stableHash(value) { let hash = 2166136261; for (const char of String(value)) { hash ^= char.codePointAt(0); hash = Math.imul(hash, 16777619) } return hash >>> 0 }
function seededPosition(id, index) { return { x: ((stableHash(`${id}:x:${index}`) / 0xffffffff) * 2 - 1) * 18, y: ((stableHash(`${id}:y:${index}`) / 0xffffffff) * 2 - 1) * 18 } }
function parseColor(value) { const text = String(value || '').trim(); const hex = text.match(/^#([0-9a-f]{6})$/i); if (hex) return [parseInt(hex[1].slice(0,2),16), parseInt(hex[1].slice(2,4),16), parseInt(hex[1].slice(4,6),16)]; const rgb = text.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i); return rgb ? rgb.slice(1, 4).map(Number) : null }
function mix(fg, amount, bg) { const a = parseColor(fg) || [166,166,166]; const b = parseColor(bg) || [255,255,255]; const v = Math.max(0, Math.min(1, Number(amount) || 0)); return `#${a.map((x, i) => Math.round(x * v + b[i] * (1 - v)).toString(16).padStart(2,'0')).join('')}` }
function refreshTheme() { const bg = paletteFromBridge?.background || '#FFFFFF'; const label = paletteFromBridge?.label || '#171B23'; Object.assign(colors, paletteFromBridge?.types || {}); theme = { background: bg, label, dimNode: mix('#A6A6A6', .1, bg), dimEdge: mix('#8C8C8C', .12, bg), focusEdge: paletteFromBridge?.line || mix('#8C8C8C', .45, bg) }; if (graph) graph.forEachNode((id) => graph.setNodeAttribute(id, 'color', colors[graph.getNodeAttribute(id, 'type')] || colors.reference)); renderer?.setSetting('labelColor', { color: theme.label }); renderer?.refresh() }
function normalize(node, index) { const id = String(node.id || node.name || `memory-${index}`); const pos = seededPosition(id, index); const type = colors[node.type] ? node.type : 'reference'; return { id, label: String(node.title || id), title: String(node.title || id), type, source: String(node.source || ''), tags: Array.isArray(node.tags) ? node.tags : [], x: Number.isFinite(node.x) ? node.x : pos.x, y: Number.isFinite(node.y) ? node.y : pos.y, baseX: Number.isFinite(node.x) ? node.x : pos.x, baseY: Number.isFinite(node.y) ? node.y : pos.y, phase: stableHash(`${id}:float`) % 6283 / 1000, color: colors[type] } }
function nodeMatch(data) { const q = query.trim().toLocaleLowerCase(); if (!q) return true; return [data.id, data.title, data.source, ...(data.tags || [])].some((value) => String(value || '').toLocaleLowerCase().includes(q)) }
// v1.5.0：reducer 不再掺漂浮偏移（sigma v3 的 reducer 输出不进 WebGL 缓冲），
// 漂浮由 floatTick 直接写 graphology 坐标实现，reducer 只管渲染态。
// size 同理：呼吸引擎已把收放值写进 graphology 的 size 属性，reducer 只在
// 漂移未接管时（大图/关开关）兜底用静态公式，否则尊重已写入的呼吸 size。
function nodeReducer(node, data) { const focused = !hovered || node === hovered || hoveredNeighbors.has(node); const match = nodeMatch(data); const dimmed = !focused || !match; const degree = graph?.degree(node) || 0; const staticSize = (4 + Math.sqrt(degree) * 2) * Number(graphSettings.nodeScale || 1); const size = floatBase.has(node) && Number.isFinite(data.size) ? data.size : staticSize; return { ...data, size, color: dimmed ? theme.dimNode : data.color, label: dimmed ? null : data.label, forceLabel: node === hovered } }
function edgeReducer(edge, data) { const [source, target] = graph.extremities(edge); const linked = hovered && (source === hovered || target === hovered); const color = linked ? mix(graph.getNodeAttributes(hovered)?.color || '#A6A6A6', .6, theme.background) : (hovered ? theme.dimEdge : (data.kind === '共同标签' ? mix('#B4B4B4', .3, theme.background) : theme.focusEdge)); return { ...data, color, size: linked ? 1.6 : 1 } }
// v1.6.0：悬停标签去掉背景描边（暗色模式下浅色描边导致看不清），改为放大加粗
// 注意：sigma 的 drawLabel data 没有 node 字段，用 data.forceLabel 判断（nodeReducer 里已设置）
function drawLabel(context, data, settings) {
  if (!data.label) return
  context.save()
  const isHovered = data.forceLabel === true
  const size = isHovered ? settings.labelSize * 1.3 : settings.labelSize
  const weight = isHovered ? '700' : settings.labelWeight
  context.font = `${weight} ${size}px ${settings.labelFont}`
  // 去掉 strokeText 描边（那个"背景条"在暗色模式下是浅色导致标签同色看不见）
  // Node colors describe the type, not the text. Ordinary labels always use
  // the palette label color so dark/light theme changes remain readable.
  context.fillStyle = theme.label
  context.fillText(data.label, data.x + data.size + 3, data.y + size / 3)
  context.restore()
}
// v1.7.2：悬停时 sigma 默认会用 defaultDrawNodeHover 再画一个带背景的小字标签，
// 和加粗大字标签重复且互相遮挡（用户截图反馈）。置空它：悬停高亮圈（WebGL 层）
// 与 DOM 悬停弹窗不受影响，只去掉重复的小药丸标签。
function drawHover(_context, _data, _settings) {}
function edgeKey(source, target, kind) { const pair = [source, target].sort(); return `${kind}:${pair[0]}::${pair[1]}` }
function syncGraph(data) { graph = new Graph({ type: 'undirected', multi: true }); const selected = graphSettings.selectedTypes || {}; data.nodes.filter((node) => selected[node.type] !== false).forEach((node, index) => { const item = normalize(node, index); graph.addNode(item.id, item) }); const distance = Number(graphSettings.forces?.distance || 80); const distanceMultiplier = 2 - (distance / 160) * 1.5; data.edges.forEach((edge) => { const source = String(edge.source); const target = String(edge.target); if (!graph.hasNode(source) || !graph.hasNode(target) || source === target) return; const kind = edge.kind || '双链'; const key = edgeKey(source, target, kind); if (!graph.hasEdge(key)) { const baseWeight = kind === '共同标签' ? .5 : 2; graph.addEdgeWithKey(key, source, target, { kind, baseWeight, weight: baseWeight * distanceMultiplier, size: 1 }) } }); if (graphSettings.showOrphans === false) graph.forEachNode((id) => { if (graph.degree(id) === 0) graph.dropNode(id) }); updateNodeList() }
function updateNodeList() { if (!nodeList || !graph) return; nodeList.replaceChildren(); const nodes = []; graph.forEachNode((id, data) => nodes.push({ id, title: data.title, type: typeLabels[data.type] || data.type })); nodes.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN')); for (const item of nodes) { const option = document.createElement('option'); option.value = item.id; option.textContent = `${item.title} · ${item.type}`; nodeList.append(option) } nodeBrowser.hidden = nodes.length === 0 }
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
function bindRenderer() { renderer.on('enterNode', ({ node, event }) => { hovered = node; hoveredNeighbors = new Set([node, ...graph.neighbors(node)]); if (nodeList) nodeList.value = node; showTooltip(node, event); renderer.refresh() }); renderer.on('leaveNode', clearHover); renderer.on('clickNode', ({ node }) => bridge?.openMemory(node)); renderer.on('clickStage', clearHover); renderer.on('doubleClickStage', () => renderer.getCamera().animatedReset({ duration: 300 })); renderer.on('downNode', ({ node, event }) => { pauseFloat(); renderer.getCamera().disable(); event.preventSigmaDefault(); event.original.preventDefault(); layout?.start(); renderer.getMouseCaptor().on('mousemovebody', moveNode); renderer.getMouseCaptor().once('mouseup', () => { renderer.getCamera().enable(); renderer.getMouseCaptor().removeListener('mousemovebody', moveNode); if (layout) window.setTimeout(() => { layout?.stop(); layout = null; snapshotFloatBase(); syncFloat() }, 1800); else reheatAfterDrag(); resumeFloat() }); function moveNode(mouseEvent) { markInteraction(); const position = renderer.viewportToGraph(mouseEvent); graph.setNodeAttribute(node, 'x', position.x); graph.setNodeAttribute(node, 'y', position.y); graph.setNodeAttribute(node, 'baseX', position.x); graph.setNodeAttribute(node, 'baseY', position.y); floatBase.set(node, { x: position.x, y: position.y }); renderer.refresh() } }); renderer.getMouseCaptor().on('mousedown', pauseFloat); renderer.getMouseCaptor().on('mouseup', resumeFloat)
// v1.7.4：滚轮缩放不再绑定 markInteraction——旧逻辑把 wheel 记为"交互"，
// floatTick 在交互后 900ms 内直接 return，导致缩放期间呼吸冻结、停手约 1s
// 才恢复。缩放只是相机矩阵变化，不冲突坐标写入；幅度换算改由 floatTick
// 每帧调 updateFloatScale 实时跟踪缩放比，动画全程连续。
}
function render(data) { raw = data; syncGraph(data); $('#node-count').textContent = String(graph.order); $('#edge-count').textContent = String(graph.size); // v1.7.2：仓库已配置但没有任何记忆时，给出下一步指引而不是卡在"正在读取"
  if (graph.order === 0) message.textContent = '仓库中暂无记忆条目：在「记忆仓库」新建或导入后，这里会展示关系图。'; message.classList.toggle('hidden', graph.order > 0); refreshTheme(); if (!renderer) { renderer = new Sigma(graph, $('#sigma-container'), { renderLabels: true, labelRenderedSizeThreshold: Number(graphSettings.labelThreshold || 8), labelFont: 'Segoe UI, Microsoft YaHei, sans-serif', labelSize: 12, labelWeight: '500', labelColor: { color: theme.label }, defaultNodeColor: '#A6A6A6', defaultEdgeColor: theme.focusEdge, defaultNodeType: 'circle', nodeProgramClasses: programs, defaultDrawNodeLabel: drawLabel, defaultDrawNodeHover: drawHover, nodeReducer, edgeReducer, hideEdgesOnMove: graph.size > 8000, stagePadding: 28, zIndex: true }); bindRenderer() } else renderer.setGraph(graph); startLayout(); window.mshubGraphReady = true; window.mshubGraphNodeCount = graph.order; window.mshubGraphEdgeCount = graph.size }
function load() { if (!bridge) return; message.textContent = '正在读取记忆关系…'; message.classList.remove('hidden'); const kinds = $('#include-tags').checked ? 'link,tag' : 'link'; bridge.getGraph(kinds, (payload) => { let data = null; try { data = JSON.parse(payload) } catch (error) { message.textContent = `图谱数据解析失败：${error}`; return } // v1.7.2：仓库未配置/读取失败时返回带 unavailable 标记的结构化载荷，给出人话提示而不是 JSON 报错
  if (data && data.unavailable) { message.textContent = data.unavailable === 'repo-not-set' ? '尚未配置仓库路径，记忆图示暂无法显示。请先在「设置选项 → 仓库与语言」选择仓库根目录并保存。' : `仓库读取失败：${data.message || '未知错误'}`; return } render(data) }) }
window.mshubSetTheme = (mode) => { const value = mode === 'dark' ? 'dark' : 'light'; document.documentElement.dataset.theme = value; document.body.dataset.theme = value; const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = value === 'dark' ? '#0B0E14' : '#F2F4F8'; refreshTheme() }
window.mshubSetPalette = (payload) => { try { paletteFromBridge = typeof payload === 'string' ? JSON.parse(payload) : payload; window.mshubSetTheme(paletteFromBridge.theme); } catch {} }
window.mshubSetGraphSettings = (payload) => { try { graphSettings = mergeSettings(typeof payload === 'string' ? JSON.parse(payload) : payload); saveSettings(); load() } catch {} }
// ---- v1.5.0 呼吸引擎 ----------------------------------------------------
// 目标观感：每个记忆点像呼吸灯——大小一收一放 + 位置小幅起伏，节奏错开。
// 双通道都走 rAF 直写 graphology 坐标 + size（v1.4.2 的 reducer 偏移不上屏，
// 详见 RELEASE_NOTES）。基准位 = FA2 收敛/拖拽后的坐标（floatBase 快照）。
// 呼吸曲线用非对称波形（吸快呼慢、末端微顿），比等速 sin 更像"呼吸"。
function breathWave(t) {
  // t ∈ [0,1) 一个呼吸周期。前 40% 吸气（快）、后 60% 呼气（慢+末端停顿）。
  // 输出 [0,1] 平滑曲线，两端导数≈0（无顿挫）。
  const p = t - Math.floor(t)
  const u = p < 0.4 ? p / 0.4 : 1 - (p - 0.4) / 0.6
  return u * u * (3 - 2 * u)  // smoothstep
}
function floatSeedFor(nodeId) {
  let seed = floatSeeds.get(nodeId)
  if (!seed) {
    const h1 = stableHash(`${nodeId}:x`)
    const h2 = stableHash(`${nodeId}:y`)
    const h3 = stableHash(`${nodeId}:a`)
    const h4 = stableHash(`${nodeId}:s`)
    seed = {
      phaseX: (h1 % 6283) / 1000,
      phaseY: (h2 % 6283) / 1000,
      // 呼吸相位（大小收放的起始点），按 id 错开
      phaseB: ((h4 >>> 4) % 6283) / 1000,
      periodX: 3600 + (h1 % 3000),
      periodY: 4100 + ((h2 >>> 8) % 2900),
      // 呼吸周期 3.5~5.5s——motion-design 建议环境动效 3-5s，接近人类静息呼吸（12~17 次/分）
      periodB: 3500 + (h3 % 2000),
      // 位置起伏幅度 8~14 屏幕像素——肉眼明确可感的漂浮感
      amplitudePx: 8 + (h3 % 100) / 100 * 6,
      // 大小呼吸幅度：半径收放 ±22%~38%——呼吸灯式的一收一放，主通道
      sizeAmp: 0.22 + (h4 % 100) / 100 * 0.16,
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
  const perPx = floatGraphPerPx
  const nodeScale = Number(graphSettings.nodeScale || 1)
  graph.forEachNode((id, attrs) => {
    const base = floatBase.get(id) || attrs
    const seed = floatSeedFor(id)
    // 位置通道：x/y 各自独立的缓慢起伏
    const x = base.x + Math.sin(floatTime / seed.periodX + seed.phaseX) * seed.amplitudePx * perPx
    const y = base.y + Math.cos(floatTime / seed.periodY + seed.phaseY) * seed.amplitudePx * perPx
    // 大小通道：呼吸波驱动半径收放。size 基数与 nodeReducer 一致
    // （4 + sqrt(degree)*2），乘以 nodeScale 与 (1 ± sizeAmp·breath)。
    const degree = graph.degree(id)
    const baseSize = (4 + Math.sqrt(degree) * 2) * nodeScale
    const breath = breathWave(floatTime / seed.periodB + seed.phaseB)
    const size = baseSize * (1 - seed.sizeAmp + seed.sizeAmp * 2 * breath)
    graph.setNodeAttribute(id, 'x', x)
    graph.setNodeAttribute(id, 'y', y)
    graph.setNodeAttribute(id, 'size', size)
  })
}
function floatTick(now) {
  floatFrame = requestAnimationFrame(floatTick)
  const idleFor = now - lastInteraction
  // A missed mouseup must not permanently disable motion. After one second
  // of no pointer activity the timestamp is authoritative and stale depth is
  // cleared as a safety net.
  if (interactionDepth && idleFor >= 1000) interactionDepth = 0
  if (interactionDepth || idleFor < 900 || !graph || !renderer) return
  // 拖拽/平移/缩放时 sigma 自己会触发渲染；静止期由这里驱动增量渲染。
  if (!floatLastTick) floatLastTick = now
  floatTime += Math.min(64, now - floatLastTick)  // 帧率波动时步长封顶，漂浮不跳变
  floatLastTick = now
  // v1.7.4：每帧跟踪缩放比（开销两次 viewportToGraph）。滚轮缩放期间相机
  // 比例连续变化，若仍按交互结束后才刷新，缩放中屏幕位移幅度会漂移/放大。
  updateFloatScale()
  applyFloatFrame()
}
function syncFloat() {
  const enabled = graph && graph.order <= 3000 && graph.size <= 8000 && !reduceMotion && readMotionSetting()
  if (enabled && !floatFrame) { floatLastTick = 0; updateFloatScale(); floatFrame = requestAnimationFrame(floatTick) }
  if (!enabled && floatFrame) stopFloat()
}
function stopFloat() { if (floatFrame) { cancelAnimationFrame(floatFrame); floatFrame = 0 }; floatLastTick = 0 }
function markInteraction() {
  lastInteraction = performance.now()
  if (floatResumeTimer) window.clearTimeout(floatResumeTimer)
  floatResumeTimer = window.setTimeout(() => {
    interactionDepth = 0
    // Preserve the diagnostic timestamp while allowing the next frame to run.
    lastInteraction = performance.now() - 1000
    updateFloatScale()
  }, 1100)
}
function pauseFloat() { interactionDepth = Math.min(interactionDepth + 1, 4); markInteraction() }
function resumeFloat() { interactionDepth = Math.max(0, interactionDepth - 1); markInteraction(); updateFloatScale() }
window.mshubReloadGraph = () => load()
// v1.5.1 诊断接口：smoke-float 用它分辨"数据没到页面"与"渲染为 0"。
window.mshubDiagCount = () => JSON.stringify({ rawNodes: raw.nodes.length, rawEdges: raw.edges.length, graphOrder: graph?.order ?? -1, graphSize: graph?.size ?? -1, driftTime: Math.round(floatTime), floatBaseSize: floatBase.size })
// v1.6.0 呼吸诊断：确认 rAF 循环是否活着、为什么没推进 floatTime
window.mshubDiagFloat = () => JSON.stringify({
  rafActive: !!floatFrame,
  floatTime: Math.round(floatTime),
  floatLastTick: Math.round(floatLastTick),
  interactionDepth,
  lastInteraction: Math.round(lastInteraction),
  now: Math.round(performance.now()),
  sinceInteraction: Math.round(performance.now() - lastInteraction),
  floatBaseSize: floatBase.size,
  graphOrder: graph?.order ?? -1,
  reduceMotion,
  motionEnabled: readMotionSetting(),
})
window.mshubDiagBridge = (cb) => { try { bridge?.getGraph('link', (p) => { try { const d = JSON.parse(p); cb(JSON.stringify({ payloadNodes: d.nodes?.length ?? -1, payloadLen: p.length })) } catch (e) { cb('parse-err:' + e) } }) } catch (e) { cb('call-err:' + e) } }
function openSelectedNode() { const id = nodeList?.value; if (id) bridge?.openMemory(id) }
$('#query').addEventListener('input', (event) => { query = event.target.value; renderer?.refresh() })
$('#clear').addEventListener('click', () => { $('#query').value = ''; query = ''; renderer?.refresh() })
$('#refresh').addEventListener('click', load)
$('#reset').addEventListener('click', () => renderer?.getCamera().animatedReset({ duration: 300 }))
$('#zoom-in').addEventListener('click', () => renderer?.getCamera().animatedZoom({ factor: .75, duration: 220 }))
$('#zoom-out').addEventListener('click', () => renderer?.getCamera().animatedUnzoom({ factor: .75, duration: 220 }))
nodeList?.addEventListener('change', () => { const id = nodeList.value; if (id && graph?.hasNode(id)) { hovered = id; hoveredNeighbors = new Set([id, ...graph.neighbors(id)]); renderer?.refresh() } })
openNode?.addEventListener('click', openSelectedNode)
graphSettings = mergeSettings(readSettings())
reduceMotion = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
$('#include-tags').checked = Boolean(graphSettings.includeTags)
$('#include-tags').addEventListener('change', () => { graphSettings.includeTags = $('#include-tags').checked; saveSettings(); load() })
window.matchMedia?.('(prefers-reduced-motion: reduce)').addEventListener?.('change', (event) => { reduceMotion = event.matches; if (reduceMotion) stopFloat(); else syncFloat() })
if (window.QWebChannel && window.qt?.webChannelTransport) new QWebChannel(window.qt.webChannelTransport, (channel) => { bridge = channel.objects.mshub; bridge.getPalette((payload) => { try { window.mshubSetPalette(payload); } catch {} }); bridge.readGraphSettings((payload) => { try { graphSettings = mergeSettings(JSON.parse(payload)); $('#include-tags').checked = Boolean(graphSettings.includeTags); syncSettingsPanel(); } catch {} }); load() })
else { message.textContent = '图谱桥接未就绪（请从 Qt WebEngine 打开）。' }

function bindSettingsPanel() {
  const panel = $('#graph-settings'); const toggle = $('#settings-toggle');
  // v1.7.5 修复：面板浮层盖住工具栏"设置"按钮后没有任何关闭出口（死胡同）。
  // closePanel 统一收口：保存并关闭按钮、Esc、点击面板外区域三条路都走这里。
  const closePanel = () => { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false') }
  toggle.addEventListener('click', () => { panel.hidden = !panel.hidden; toggle.setAttribute('aria-expanded', String(!panel.hidden)) })
  $('#save-settings')?.addEventListener('click', () => { saveSettings(); closePanel() })
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) closePanel() })
  document.addEventListener('pointerdown', (event) => {
    if (panel.hidden || panel.contains(event.target) || toggle.contains(event.target)) return
    closePanel()
  })
  const types = panel.querySelectorAll('[data-type]'); types.forEach((input) => input.addEventListener('change', () => { graphSettings.selectedTypes[input.dataset.type] = input.checked; saveSettings(); load() }))
  const orphan = $('#show-orphans'); orphan.addEventListener('change', () => { graphSettings.showOrphans = orphan.checked; saveSettings(); load() })
  const motion = $('#motion-toggle'); motion.checked = readMotionSetting(); motion.addEventListener('change', () => { localStorage.setItem(motionKey, JSON.stringify({ enabled: motion.checked })); if (!motion.checked) stopFloat(); else { snapshotFloatBase(); syncFloat() } })
  // v1.7.3：修复存量 bug——单键设置（nodeScale/labelThreshold）split 后 key=undefined，
  // 值被写进 graphSettings[undefined]，这两个滑杆从 v1.5 起就没真正生效（显示 min-max 中点）。
  const settingKeyOf = (name) => { const parts = name.split('.'); return parts.length === 2 ? ['nested', parts[0], parts[1]] : ['flat', parts[0], parts[0]] }
  panel.querySelectorAll('[data-setting]').forEach((input) => input.addEventListener('input', () => { const [kind, group, key] = settingKeyOf(input.dataset.setting); if (kind === 'nested') graphSettings[group][key] = Number(input.value); else graphSettings[key] = Number(input.value); input.nextElementSibling.textContent = input.value; saveSettings(); if (kind === 'nested' && group === 'forces') { applyForceSettings(); startLayout(); } if (key === 'labelThreshold') renderer?.setSetting('labelRenderedSizeThreshold', Number(input.value)); renderer?.refresh() }))
  // v1.7.3：恢复默认——清本地与 Qt 两侧的已存设置，回到 DEFAULT_GRAPH_SETTINGS 并重载图谱
  const reset = $('#reset-settings')
  reset?.addEventListener('click', () => {
    try { localStorage.removeItem(settingsKey); bridge?.writeGraphSettings(JSON.stringify(DEFAULT_GRAPH_SETTINGS)) } catch {}
    graphSettings = mergeSettings({})
    $('#include-tags').checked = Boolean(graphSettings.includeTags)
    syncSettingsPanel()
    renderer?.setSetting('labelRenderedSizeThreshold', Number(graphSettings.labelThreshold || 8))
    load()
  })
  syncSettingsPanel()
}
function syncSettingsPanel() { const panel = $('#graph-settings'); if (!panel) return; panel.querySelectorAll('[data-setting]').forEach((input) => { const parts = input.dataset.setting.split('.'); input.value = parts.length === 2 ? graphSettings[parts[0]][parts[1]] : graphSettings[parts[0]]; input.nextElementSibling.textContent = input.value }); panel.querySelectorAll('[data-type]').forEach((input) => { input.checked = graphSettings.selectedTypes[input.dataset.type] !== false }); $('#show-orphans').checked = graphSettings.showOrphans !== false; $('#motion-toggle').checked = readMotionSetting() }
bindSettingsPanel()
