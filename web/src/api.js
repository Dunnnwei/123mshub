export function formatErrorDetail(detail) {
  // FastAPI 422 校验错误的 detail 是对象数组，直接 new Error() 会显示成 [object Object]。
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const where = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== 'body').join('.') : ''
        return where ? `${where}：${item?.msg || '格式不正确'}` : (item?.msg || '格式不正确')
      })
      .join('；')
  }
  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || JSON.stringify(detail)
  }
  return detail || ''
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  let data
  try {
    data = await response.json()
  } catch {
    data = null
  }
  if (!response.ok) {
    const detail = formatErrorDetail(data?.detail)
    throw new Error(detail || `请求失败（${response.status}）`)
  }
  return data
}

export const api = {
  health: () => request('/api/health'),
  config: () => request('/api/config'),
  aiPresets: () => request('/api/config/ai-presets'),
  saveConfig: (body) => request('/api/config', { method: 'PUT', body: JSON.stringify(body) }),
  selectDirectory: () => request('/api/system/select-directory', { method: 'POST' }),
  openDirectory: (name) => request('/api/system/open-directory', { method: 'POST', body: JSON.stringify({ name }) }),
  listSkills: () => request('/api/skills'),
  listTags: () => request('/api/tags'),
  skill: (name, library = '') => request(`/api/skills/detail?name=${encodeURIComponent(name)}&library=${encodeURIComponent(library)}`),
  saveTags: (name, tags, library = '') => request('/api/skills/tags', {
    method: 'PUT',
    body: JSON.stringify({ name, tags, library }),
  }),
  updateMetadata: (name, body, library = '') => request('/api/skills/metadata', {
    method: 'PUT',
    // name 放在展开之后：body 里可能带 name: undefined，顺序反了会把有效值覆盖掉
    body: JSON.stringify({ ...body, name, library }),
  }),
  translateOne: (name, library = '') => request('/api/skills/translate', { method: 'POST', body: JSON.stringify({ name, library }) }),
  startTranslate: (names) => request('/api/jobs/translate', { method: 'POST', body: JSON.stringify({ names: names ?? null }) }),
  preview: (body) => request('/api/skills/preview', { method: 'POST', body: JSON.stringify(body) }),
  install: (body) => request('/api/skills', { method: 'POST', body: JSON.stringify(body) }),
  checkVersion: (name, library = '') => request('/api/skills/check-version', { method: 'POST', body: JSON.stringify({ name, library }) }),
  update: (name, library = '') => request('/api/skills/update', { method: 'POST', body: JSON.stringify({ name, library }) }),
  changeMode: (name, mode, library = '') => request('/api/skills/change-mode', { method: 'POST', body: JSON.stringify({ name, mode, library }) }),
  scan: (body) => request('/api/skills/scan', { method: 'POST', body: JSON.stringify(body) }),
  jobs: () => request('/api/jobs'),
  dismissJob: (jobId) => request('/api/jobs/dismiss', { method: 'POST', body: JSON.stringify({ job_id: jobId }) }),
  clearFinishedJobs: () => request('/api/jobs/clear-finished', { method: 'POST' }),
  startInstall: (body) => request('/api/jobs/install', { method: 'POST', body: JSON.stringify(body) }),
  startScan: (body) => request('/api/jobs/scan', { method: 'POST', body: JSON.stringify(body) }),
  startUpdate: (name, library = '') => request('/api/jobs/update', { method: 'POST', body: JSON.stringify({ name, library }) }),
  trust: (name, library = '') => request('/api/skills/trust', { method: 'POST', body: JSON.stringify({ name, library }) }),
  aiModels: (baseUrl, key) => request('/api/ai/models', { method: 'POST', body: JSON.stringify({ ai_base_url: baseUrl, ai_key: key }) }),
  remove: (name, library = '') => request('/api/skills/delete', { method: 'POST', body: JSON.stringify({ name, library }) }),
  prompt: (name, library = '') => request(`/api/skills/install-prompt?name=${encodeURIComponent(name)}&library=${encodeURIComponent(library)}`),
  libraryPrompt: () => request('/api/repository/library-prompt'),
  rebuild: () => request('/api/index/rebuild', { method: 'POST' }),
  reconcile: () => request('/api/repository/reconcile', { method: 'POST' }),
  migrateManifests: () => request('/api/repository/migrate-manifests', { method: 'POST' }),

// ---- 记忆库（Memory）----
  memoryEntries: (params = {}) => {
    const query = new URLSearchParams()
    if (params.type) query.set('type', params.type)
    if (params.q) query.set('q', params.q)
    if (params.sort) query.set('sort', params.sort)
    const suffix = query.toString()
    return request(`/api/memory/entries${suffix ? `?${suffix}` : ''}`)
  },
  memoryEntry: (name) => request(`/api/memory/entries/${encodeURIComponent(name)}`),
  createMemoryEntry: (body) => request('/api/memory/entries', { method: 'POST', body: JSON.stringify(body) }),
  updateMemoryEntry: (name, body) => request(`/api/memory/entries/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  }),
  deleteMemoryEntry: (name) => request(`/api/memory/entries/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  memoryInbox: () => request('/api/memory/inbox'),
  admitMemoryInbox: (file, body) => request(`/api/memory/inbox/${encodeURIComponent(file)}/admit`, {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  discardMemoryInbox: (file) => request(`/api/memory/inbox/${encodeURIComponent(file)}/discard`, { method: 'POST' }),
  discardAllMemoryInbox: () => request('/api/memory/inbox/discard-all', { method: 'POST' }),
  memoryAiDraft: (body) => request('/api/memory/ai-draft', { method: 'POST', body: JSON.stringify({ body }) }),
  memoryStats: () => request('/api/memory/stats'),
  memoryIndexFile: () => request('/api/memory/index-file'),
  memoryRebuild: () => request('/api/memory/rebuild', { method: 'POST' }),
  memoryTidy: (useAi = true) => request('/api/memory/tidy', {
    method: 'POST',
    body: JSON.stringify({ use_ai: useAi }),
  }),
  memoryReports: () => request('/api/memory/reports'),
  memoryReport: (file) => request(`/api/memory/reports/${encodeURIComponent(file)}`),
  memoryDutyPrompt: () => request('/api/memory/duty-prompt'),
  migrationScan: (path) => request('/api/migration/scan', {
    method: 'POST',
    body: JSON.stringify({ path }),
  }),
  migrationRun: (path, options = {}) => request('/api/migration/run', {
    method: 'POST',
    body: JSON.stringify({
      path,
      include_memory: options.includeMemory !== false,
      include_skills: options.includeSkills !== false,
    }),
  }),
}
