// Choose the 123ui5.0 Indigo/Violet values for the largest categories in the
// full dataset. Filters do not reorder colors; legend and nodes share mapping.
export function rankedTypeColors(nodes, dark = false) {
  const types = ['user', 'project', 'reference', 'feedback']
  const counts = Object.fromEntries(types.map(type => [type, 0]))
  for (const node of nodes || []) counts[types.includes(node.type) ? node.type : 'reference'] += 1
  const ranked = [...types].sort((a, b) => counts[b] - counts[a] || types.indexOf(a) - types.indexOf(b))
  const palette = dark
    ? ['#818CF8', '#A78BFA', '#7C3AED', '#C4B5FD']
    : ['#6366F1', '#7C3AED', '#8B5CF6', '#A78BFA']
  return Object.fromEntries(ranked.map((type, index) => [type, palette[index]]))
}
