/* HAUI visual adapter around the retained, verified Sigma runtime. No graph physics changes. */
window.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement
  const data = window.mshubHaui
  const properties = { bg: 'bg', sidebar: 'sidebar', surface: 'surface', raised: 'raised',
    ink: 'ink', muted: 'muted', faint: 'faint', line: 'line', strong: 'strong', blue: 'action',
    accent: 'accent', selection: 'selection', dim: 'inset', edge: 'graph_line',
    'graph-bg': 'bg', 'on-action': 'on_action', hover: 'hover', control: 'control',
    user: 'user', project: 'project', reference: 'reference', feedback: 'feedback' }
  function apply(payload) {
    const value = typeof payload === 'string' ? JSON.parse(payload) : payload
    const p = value?.controls || data[value?.theme === 'dark' ? 'dark' : 'light']
    for (const [css, token] of Object.entries(properties)) root.style.setProperty(`--${css}`, p[token])
    root.dataset.designSystem = 'HAUI'
    root.style.colorScheme = value?.theme === 'dark' ? 'dark' : 'light'
  }
  const setPalette = window.mshubSetPalette
  window.mshubSetPalette = payload => { setPalette?.(payload); apply(payload) }
  const icon = name => data.icons[name]?.replaceAll('COLOR', 'currentColor') || ''
  for (const [id, name] of Object.entries({ refresh: 'refresh', reset: 'auto', 'settings-toggle': 'settings',
    clear: 'close', 'open-node': 'open', 'save-settings': 'save' })) {
    const button = document.getElementById(id)
    if (button) button.insertAdjacentHTML('afterbegin', icon(name))
  }
  const search = document.querySelector('.search > span')
  if (search) search.innerHTML = icon('search')
  apply({ theme: root.dataset.theme || 'light' })
}, { once: true })
