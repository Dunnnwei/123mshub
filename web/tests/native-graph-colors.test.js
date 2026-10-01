import test from 'node:test'
import assert from 'node:assert/strict'
import { rankedTypeColors } from '../native-graph/colors.js'

test('dominant categories get brand colors regardless of taxonomy', () => {
  const nodes = [...Array(12).fill({ type: 'reference' }), ...Array(5).fill({ type: 'feedback' }), { type: 'user' }, { type: 'project' }]
  const light = rankedTypeColors(nodes)
  const dark = rankedTypeColors(nodes, true)
  assert.equal(light.reference, '#6366F1')
  assert.equal(light.feedback, '#7C3AED')
  assert.equal(dark.reference, light.reference)
  assert.equal(dark.feedback, light.feedback)
  assert.equal(new Set(Object.values(light)).size, 4)
  assert.deepEqual(Object.values(dark).sort(), ['#6366F1', '#7C3AED', '#FB7185', '#34D399'].sort())
})

test('tie order is stable and unknown node types count as reference', () => {
  assert.deepEqual(rankedTypeColors([{ type: 'unknown' }]), rankedTypeColors([{ type: 'reference' }]))
  assert.equal(rankedTypeColors([]).user, '#6366F1')
  assert.equal(rankedTypeColors([]).project, '#7C3AED')
})
