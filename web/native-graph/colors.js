// Choose the two brand colors for the largest categories in the full dataset.
// Filters do not reorder colors; legend and nodes always share this mapping.
export function rankedTypeColors(nodes, dark = false) {
  const types = ['user', 'project', 'reference', 'feedback']
  const counts = Object.fromEntries(types.map(type => [type, 0]))
  for (const node of nodes || []) counts[types.includes(node.type) ? node.type : 'reference'] += 1
  const ranked = [...types].sort((a, b) => counts[b] - counts[a] || types.indexOf(a) - types.indexOf(b))
  const palette = ['#6366F1', '#7C3AED', dark ? '#FB7185' : '#F43F5E', dark ? '#34D399' : '#22C55E']
  return Object.fromEntries(ranked.map((type, index) => [type, palette[index]]))
}
