import test from 'node:test'
import assert from 'node:assert/strict'
import { rankedTypeColors } from '../native-graph/colors.js'

test('dominant categories get deterministic 123ui5.0 Indigo/Violet colors', () => {
  const nodes = [...Array(12).fill({ type: 'reference' }), ...Array(5).fill({ type: 'feedback' }), { type: 'user' }, { type: 'project' }]
  const light = rankedTypeColors(nodes)
  const dark = rankedTypeColors(nodes, true)
  assert.equal(light.reference, '#6366F1')
  assert.equal(light.feedback, '#7C3AED')
  assert.equal(dark.reference, '#818CF8')
  assert.equal(dark.feedback, '#A78BFA')
  assert.equal(new Set(Object.values(light)).size, 4)
  assert.deepEqual(Object.values(dark).sort(), ['#818CF8', '#A78BFA', '#7C3AED', '#C4B5FD'].sort())
})

test('tie order is stable and unknown node types count as reference', () => {
  assert.deepEqual(rankedTypeColors([{ type: 'unknown' }]), rankedTypeColors([{ type: 'reference' }]))
  assert.equal(rankedTypeColors([]).user, '#6366F1')
  assert.equal(rankedTypeColors([]).project, '#7C3AED')
})
