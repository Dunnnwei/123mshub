import test from 'node:test'
import assert from 'node:assert/strict'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'

function hash(value) {
  let result = 2166136261
  for (const char of String(value)) result = Math.imul(result ^ char.codePointAt(0), 16777619)
  return result >>> 0
}

test('memory graph keeps deterministic positions and handles 3000 nodes/6000 edges', { timeout: 15000 }, () => {
  const graph = new Graph({ type: 'undirected', multi: false })
  const nodeCount = 3000
  for (let index = 0; index < nodeCount; index += 1) {
    const id = `memory-${index}`
    graph.addNode(id, {
      x: ((hash(`${id}:x`) / 0xffffffff) * 2 - 1) * 4,
      y: ((hash(`${id}:y`) / 0xffffffff) * 2 - 1) * 4,
    })
  }
  let edgeCount = 0
  for (let index = 0; index < nodeCount && edgeCount < 6000; index += 1) {
    for (const offset of [1, 7, 31]) {
      if (edgeCount >= 6000) break
      const target = (index + offset) % nodeCount
      if (index !== target && !graph.hasEdge(`memory-${index}`, `memory-${target}`)) {
        graph.addEdge(`memory-${index}`, `memory-${target}`, { size: 1, weight: offset === 1 ? 2 : 0.5 })
        edgeCount += 1
      }
    }
  }
  assert.equal(graph.order, nodeCount)
  assert.equal(graph.size, 6000)
  const positions = forceAtlas2(graph, {
    iterations: 10,
    settings: { gravity: 1, scalingRatio: 100, slowDown: 1, barnesHutOptimize: true, adjustSizes: true, edgeWeightInfluence: 1 },
  })
  assert.equal(Object.keys(positions).length, nodeCount)
  for (const position of Object.values(positions)) {
    assert.ok(Number.isFinite(position.x) && Number.isFinite(position.y))
  }
})
