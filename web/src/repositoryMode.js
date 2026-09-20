export function buildRepositoryRequest(form) {
  const isProject = form.item_type === 'project'
  return {
    source: form.source.trim(),
    item_type: isProject ? 'project' : 'skill',
    mode: isProject ? 'full' : form.mode,
    fetcher: isProject ? 'git' : form.fetcher,
    ref: form.ref?.trim() || null,
    subdir: isProject ? null : (form.subdir?.trim() || null),
    library: form.library || null,
  }
}
