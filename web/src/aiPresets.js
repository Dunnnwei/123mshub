export function applyAiPreset(target, preset) {
  if (!preset) return
  target.ai_provider = preset.id
  target.ai_base_url = preset.base_url
  target.ai_model = preset.model
}
