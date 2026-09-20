import test from 'node:test'
import assert from 'node:assert/strict'

import { applyAiPreset } from '../src/aiPresets.js'
import { buildRepositoryRequest } from '../src/repositoryMode.js'


test('选择 AI 供应商预设会填入 API 地址和模型', () => {
  const form = { ai_provider: 'custom', ai_base_url: '', ai_model: '' }
  const preset = {
    id: 'deepseek',
    base_url: 'https://api.deepseek.com',
    model: 'deepseek-v4-pro',
  }

  applyAiPreset(form, preset)

  assert.deepEqual(form, {
    ai_provider: 'deepseek',
    ai_base_url: 'https://api.deepseek.com',
    ai_model: 'deepseek-v4-pro',
  })
})


test('项目克隆请求强制使用 Git 全仓并清空技能子目录', () => {
  const request = buildRepositoryRequest({
    source: 'owner/app',
    item_type: 'project',
    mode: 'standard',
    fetcher: 'archive',
    ref: '',
    subdir: 'skills/demo',
  })

  assert.deepEqual(request, {
    source: 'owner/app',
    item_type: 'project',
    mode: 'full',
    fetcher: 'git',
    ref: null,
    subdir: null,
    library: null,
  })
})

test('入库请求携带目标技能库', () => {
  const request = buildRepositoryRequest({
    source: 'owner/demo',
    item_type: 'skill',
    mode: 'standard',
    fetcher: 'archive',
    ref: '',
    subdir: '',
    library: 'zcode-skills',
  })

  assert.equal(request.library, 'zcode-skills')
})
