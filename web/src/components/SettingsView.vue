<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Check, Database, Eye, EyeOff, FolderSearch, FileClock, KeyRound, LoaderCircle, RefreshCw, Save } from '@lucide/vue'
import { api } from '../api'
import { applyAiPreset } from '../aiPresets.js'
import ImportModal from './ImportModal.vue'

const props = defineProps({
  config: { type: Object, required: true },
  firstRun: { type: Boolean, default: false },
})
const emit = defineEmits(['saved', 'updated', 'toast', 'reconciled'])

const form = reactive({
  repo_root: '',
  mirrorsText: '',
  proxy: '',
  language: 'system',
  fetcher: 'archive',
  github_token: null,
  ai_base_url: '',
  ai_model: '',
  ai_provider: 'custom',
  ai_key: null,
  memory_root_override: '',
})
const saving = ref(false)
const browsing = ref(false)
const showGithubToken = ref(false)
const showAiKey = ref(false)
const error = ref('')
const clearing = ref('')
const reconciling = ref(false)
const migrating = ref(false)
const advancedOpen = ref(false)
const importOpen = ref(false)
const proxyDetecting = ref(false)
const aiPresets = computed(() => props.config.ai_presets || [])

onMounted(sync)

function sync() {
  form.repo_root = props.config.repo_root || ''
  form.mirrorsText = (props.config.mirrors || []).join('\n')
  form.proxy = props.config.proxy || ''
  form.language = props.config.language || 'system'
  form.fetcher = props.config.fetcher || 'archive'
  form.github_token = null
  form.ai_base_url = props.config.ai_base_url || 'https://api.openai.com/v1'
  form.ai_model = props.config.ai_model || 'gpt-4.1-mini'
  form.ai_provider = aiPresets.value.find(
    (item) => item.base_url.replace(/\/$/, '') === form.ai_base_url.replace(/\/$/, ''),
  )?.id || 'custom'
  form.ai_key = null
  form.memory_root_override = props.config.memory_root_override || ''
  advancedOpen.value = Boolean(form.memory_root_override)
}

function selectAiPreset() {
  if (form.ai_provider === 'custom') return
  applyAiPreset(form, aiPresets.value.find((item) => item.id === form.ai_provider))
}

async function chooseDirectory() {
  browsing.value = true
  error.value = ''
  try {
    const result = await api.selectDirectory()
    if (result.path) form.repo_root = result.path
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    browsing.value = false
  }
}

async function detectProxy() {
  proxyDetecting.value = true
  try {
    const result = await api.detectProxy()
    if (result.detected) form.proxy = result.detected
    emit('toast', result.detected
      ? { type: 'success', message: `已检测到代理：${result.detected}。请点击“保存设置”后才会生效。` }
      : { type: 'warning', message: '没有检测到可用的 HTTP/HTTPS 代理，当前草稿未改变。' })
  } catch (requestError) {
    emit('toast', { type: 'error', message: `代理检测失败：${requestError.message}` })
  } finally {
    proxyDetecting.value = false
  }
}

async function save() {
  if (!form.repo_root.trim()) {
    error.value = '请先选择技能仓库根目录。'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const payload = {
      repo_root: form.repo_root.trim(),
      mirrors: form.mirrorsText.split('\n').map((item) => item.trim()).filter(Boolean),
      proxy: form.proxy.trim(),
      language: form.language,
      fetcher: form.fetcher,
      ai_base_url: form.ai_base_url.trim(),
      ai_model: form.ai_model.trim(),
      memory_root_override: form.memory_root_override.trim(),
    }
    if (form.github_token !== null && form.github_token !== '') payload.github_token = form.github_token
    if (form.ai_key !== null && form.ai_key !== '') payload.ai_key = form.ai_key
    const result = await api.saveConfig(payload)
    emit('saved', result)
    const recovered = result.recovery?.recovered_count || 0
    emit('toast', {
      type: 'success',
      message: recovered
        ? `设置已保存，并从同步仓库识别出 ${recovered} 个已有条目。`
        : '设置已保存，仓库索引已同步。',
    })
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

async function reconcile() {
  reconciling.value = true
  error.value = ''
  try {
    const result = await api.reconcile()
    emit('reconciled')
    const memoryHeal = result.memory_heal || {}
    const memoryNote = memoryHeal.note_conflicts?.length
      ? `；记忆区隔离了 ${memoryHeal.note_conflicts.length} 个冲突副本条目（在 .meta/memory-trash/conflicts，请人工裁决）`
      : ''
    emit('toast', {
      type: 'success',
      message: result.recovered_count
        ? `已识别 ${result.recovered_count} 个同步条目，当前共 ${result.total_count} 个条目${memoryNote}。`
        : `仓库清单与记忆库已核对，当前共 ${result.total_count} 个条目${memoryNote}。`,
    })
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    reconciling.value = false
  }
}

async function migrateManifests() {
  migrating.value = true
  error.value = ''
  try {
    const result = await api.migrateManifests()
    const detail = result.errors?.length ? `（${result.errors.length} 个失败，首个：${result.errors[0]}）` : ''
    emit('toast', {
      type: result.errors?.length ? 'error' : 'success',
      message: result.migrated
        ? `已把 ${result.migrated} 个清单迁移为 _manifest.json（内容不变）${detail}`
        : `清单命名已是最新（${result.already_current || 0} 份 _manifest.json 在位），无需迁移${detail}`,
    })
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    migrating.value = false
  }
}

async function clearCredential(field) {
  clearing.value = field
  error.value = ''
  try {
    const result = await api.saveConfig({ [field]: '' })
    emit('updated', result)
    emit('toast', {
      type: 'success',
      message: field === 'github_token' ? 'GitHub Token 已清除。' : 'AI API Key 已清除。',
    })
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    clearing.value = ''
  }
}
</script>

<template>
  <section class="settings-view">
    <header class="view-heading">
      <div>
        <span v-if="firstRun" class="welcome-label">首次设置</span>
        <h1>{{ firstRun ? '先选一个本地技能仓库' : '设置' }}</h1>
        <p>{{ firstRun ? '所有 agent 都将从这个目录读取技能清单。' : '下载网络、凭据与仓库位置。' }}</p>
      </div>
    </header>

    <form class="settings-form" @submit.prevent="save">
      <section class="settings-section">
        <div class="settings-copy"><h2>界面语言</h2><p>默认跟随系统；显式选择会保存在本机设置中。AI、Agent、GitHub、API 等专用名词保持原样。</p></div>
        <div class="settings-controls"><label class="field-block"><span>语言 / Language</span><select v-model="form.language"><option value="system">跟随系统 / System</option><option value="zh-CN">中文</option><option value="en">English</option></select></label></div>
      </section>
      <section class="settings-section">
        <div class="settings-copy">
          <h2>仓库位置</h2>
          <p>SQLite、技能目录和给 agent 读取的 index.json 都保存在这里。</p>
        </div>
        <div class="settings-controls">
          <label class="field-block">
            <span>仓库根目录</span>
            <div class="input-with-button">
              <input v-model="form.repo_root" placeholder="E:\skills-repo" />
              <button class="secondary-button" type="button" :disabled="browsing" @click="chooseDirectory">
                <FolderSearch :size="16" /> 浏览
              </button>
            </div>
          </label>
          <div v-if="!firstRun" class="repository-reconcile-row">
            <button class="secondary-button" type="button" :disabled="reconciling" @click="reconcile">
              <LoaderCircle v-if="reconciling" class="spinning" :size="16" />
              <RefreshCw v-else :size="16" />
              {{ reconciling ? '识别中…' : '重新识别已同步条目' }}
            </button>
            <p>在其他机器同步文件到本目录后，可随时重建本机清单与 index.json；同时会对账记忆库（notes 条目、冲突副本隔离、MEMORY.md 重建）。</p>
          </div>
          <div v-if="!firstRun" class="repository-reconcile-row import-entry-row">
            <button class="secondary-button" type="button" @click="importOpen = true">
              <Database :size="16" /> 导入记忆技能库
            </button>
            <p>从任意目录导入：123mshub 仓库、DSH 总机（brain + memory.md）、Engramory 式索引、
              其他 agent 的散装记忆与 SKILL.md 技能目录。导入含整理去重与日报，后台执行。</p>
          </div>
          <div class="advanced-fold">
            <button
              class="advanced-fold-toggle"
              type="button"
              @click="advancedOpen = !advancedOpen"
            >{{ advancedOpen ? '收起高级选项' : '展开高级选项' }}</button>
            <div v-if="advancedOpen" class="advanced-fold-body">
              <label class="field-block">
                <span>记忆库位置覆盖（可选）</span>
                <input v-model="form.memory_root_override" placeholder="留空 = 使用 仓库根\memory" spellcheck="false" />
                <small>记忆库默认放在仓库根的 memory\ 子目录；填一个绝对路径可把它单独指到别处（如另一块盘或同步目录）。技能库与程序库不支持分设。</small>
              </label>
            </div>
          </div>
          <div v-if="!firstRun" class="repository-reconcile-row">
            <button class="secondary-button" type="button" :disabled="migrating" @click="migrateManifests">
              <LoaderCircle v-if="migrating" class="spinning" :size="16" />
              <FileClock v-else :size="16" />
              {{ migrating ? '迁移中…' : '迁移旧版清单文件' }}
            </button>
            <p>把点开头的 .manifest.json 批量改名为 _manifest.json（内容不变）。点开头文件可能会被文件同步程序排除，改名后同步程序才能收到。</p>
          </div>
          <fieldset class="inline-radio">
            <legend>默认下载方式</legend>
            <label :class="{ selected: form.fetcher === 'archive' }">
              <input v-model="form.fetcher" type="radio" value="archive" />
              <span><Check :size="13" /></span>
              Archive 压缩包
            </label>
            <label :class="{ selected: form.fetcher === 'git' }">
              <input v-model="form.fetcher" type="radio" value="git" />
              <span><Check :size="13" /></span>
              Git 浅克隆
            </label>
          </fieldset>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-copy">
          <h2>国内网络加速</h2>
          <p>镜像按顺序故障转移，全部失败后再尝试直连。代理与镜像可以叠加。</p>
        </div>
        <div class="settings-controls">
          <label class="field-block">
            <span>镜像前缀列表</span>
            <textarea v-model="form.mirrorsText" rows="3" placeholder="每行一个，例如 https://ghproxy.example/"></textarea>
            <div class="mirror-presets"><button v-for="mirror in ['https://ghproxy.link/','https://ghfast.top/']" :key="mirror" type="button" class="chip-button" @click="form.mirrorsText = form.mirrorsText ? `${form.mirrorsText}\n${mirror}` : mirror">{{ mirror }}</button></div>
            <small>支持包含 `{url}` 的模板；否则将原始地址直接拼接在前缀后。</small>
          </label>
          <label class="field-block">
            <span>HTTP / HTTPS 代理</span>
            <div class="edit-field-inline"><input v-model="form.proxy" placeholder="http://127.0.0.1:7890（可选）" /><button class="secondary-button" type="button" :disabled="proxyDetecting" @click="detectProxy">{{ proxyDetecting ? '检测中…' : '检测' }}</button></div>
            <small>检测只读取当前环境和已保存草稿，不会自动修改配置；请确认后点击保存。</small>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-copy">
          <h2>GitHub 凭据</h2>
          <p>公开仓库无需 Token。私有仓库或更高 API 限额时再填写。</p>
          <div class="credential-line">
            <span class="credential-state" :class="{ configured: config.github_token_configured }">
              <KeyRound :size="14" />
              {{ config.github_token_configured ? '已存入系统凭据管理器' : '未配置' }}
            </span>
            <button
              v-if="config.github_token_configured"
              class="clear-credential"
              type="button"
              :disabled="clearing === 'github_token'"
              @click="clearCredential('github_token')"
            >清除</button>
          </div>
        </div>
        <div class="settings-controls">
          <label class="field-block">
            <span>GitHub Token</span>
            <div class="password-field">
              <input
                v-model="form.github_token"
                :type="showGithubToken ? 'text' : 'password'"
                :placeholder="config.github_token_configured ? '留空以保留现有 Token' : 'ghp_…（可选）'"
              />
              <button type="button" :aria-label="showGithubToken ? '隐藏 Token' : '显示 Token'" @click="showGithubToken = !showGithubToken">
                <EyeOff v-if="showGithubToken" :size="17" />
                <Eye v-else :size="17" />
              </button>
            </div>
            <p v-if="showGithubToken && config.github_token_masked" class="credential-preview">
              <code>{{ config.github_token_masked }}</code>
              <span>已保存的 Token（仅隐藏中间部分）。要更换请直接输入新值。</span>
            </p>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-copy">
          <h2>AI 接口</h2>
          <p>安全审查 B 路线 + 记忆辅助（生成标题/描述、归纳整理分析）共用这一条 OpenAI 兼容线路；不填也能用，只是没有 AI 能力。</p>
          <div class="credential-line">
            <span class="credential-state" :class="{ configured: config.ai_key_configured }">
              <KeyRound :size="14" />
              {{ config.ai_key_configured ? 'API Key 已安全保存' : '未配置，可在检查时临时填写' }}
            </span>
            <button
              v-if="config.ai_key_configured"
              class="clear-credential"
              type="button"
              :disabled="clearing === 'ai_key'"
              @click="clearCredential('ai_key')"
            >清除</button>
          </div>
        </div>
        <div class="settings-controls two-column-controls">
          <label class="field-block control-wide">
            <span>常用 API 预设</span>
            <select v-model="form.ai_provider" @change="selectAiPreset">
              <option value="custom">自定义 OpenAI 兼容接口</option>
              <option v-for="preset in aiPresets" :key="preset.id" :value="preset.id">
                {{ preset.name }} · {{ preset.model }}
              </option>
            </select>
            <small v-if="form.ai_provider !== 'custom'">
              {{ aiPresets.find((item) => item.id === form.ai_provider)?.note }} 选择后仍可手动修改。
            </small>
          </label>
          <label class="field-block control-wide">
            <span>API 地址</span>
            <input v-model="form.ai_base_url" placeholder="https://api.openai.com/v1" />
          </label>
          <label class="field-block">
            <span>模型</span>
            <input v-model="form.ai_model" placeholder="gpt-4.1-mini" />
          </label>
          <label class="field-block">
            <span>API Key</span>
            <div class="password-field">
              <input
                v-model="form.ai_key"
                :type="showAiKey ? 'text' : 'password'"
                :placeholder="config.ai_key_configured ? '留空以保留现有 Key' : 'sk-…（可选）'"
              />
              <button type="button" :aria-label="showAiKey ? '隐藏 API Key' : '显示 API Key'" @click="showAiKey = !showAiKey">
                <EyeOff v-if="showAiKey" :size="17" />
                <Eye v-else :size="17" />
              </button>
            </div>
            <p v-if="showAiKey && config.ai_key_masked" class="credential-preview">
              <code>{{ config.ai_key_masked }}</code>
              <span>已保存的 Key（仅隐藏中间部分）。要更换请直接输入新值。</span>
            </p>
          </label>
        </div>
      </section>

      <div v-if="error" class="inline-error settings-error" role="alert">{{ error }}</div>
      <footer class="settings-footer">
        <button class="primary-button" type="submit" :disabled="saving">
          <LoaderCircle v-if="saving" class="spinning" :size="17" />
          <Save v-else :size="17" />
          {{ saving ? '正在保存…' : '保存设置' }}
        </button>
      </footer>
    </form>

    <ImportModal
      :open="importOpen"
      @close="importOpen = false"
      @toast="(payload) => emit('toast', payload)"
      @finished="emit('reconciled')"
    />
  </section>
</template>
