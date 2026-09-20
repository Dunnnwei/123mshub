<script setup>
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Bot, CheckCircle2, LoaderCircle, ShieldCheck, WifiOff, X } from '@lucide/vue'
import { api } from '../api'
import { applyAiPreset } from '../aiPresets.js'
import { wakeJobPolling } from '../jobStore'

const props = defineProps({
  open: { type: Boolean, default: false },
  skill: { type: Object, default: null },
  config: { type: Object, default: () => ({}) },
  initialReport: { type: Object, default: null },
})
const emit = defineEmits(['close', 'scanned', 'trust'])

const route = ref('offline')
const error = ref('')
const report = ref(null)
const aiBaseUrl = ref('')
const aiModel = ref('')
const aiKey = ref('')
const aiProvider = ref('custom')
const modelOptions = ref([])
const loadingModels = ref(false)
const aiPresets = computed(() => props.config.ai_presets || [])

watch(() => props.open, (value) => {
  if (!value) return
  route.value = 'offline'
  error.value = ''
  report.value = props.initialReport ? { ...props.initialReport } : null
  aiBaseUrl.value = props.config.ai_base_url || 'https://api.openai.com/v1'
  aiModel.value = props.config.ai_model || 'gpt-4.1-mini'
  aiProvider.value = aiPresets.value.find(
    (item) => item.base_url.replace(/\/$/, '') === aiBaseUrl.value.replace(/\/$/, ''),
  )?.id || 'custom'
  aiKey.value = ''
})

function selectAiPreset() {
  if (aiProvider.value === 'custom') return
  const target = {
    ai_provider: aiProvider.value,
    ai_base_url: aiBaseUrl.value,
    ai_model: aiModel.value,
  }
  applyAiPreset(target, aiPresets.value.find((item) => item.id === aiProvider.value))
  aiBaseUrl.value = target.ai_base_url
  aiModel.value = target.ai_model
  modelOptions.value = []
}

async function fetchModels() {
  if (!aiBaseUrl.value.trim()) {
    error.value = '请先填写网关 API 地址。'
    return
  }
  loadingModels.value = true
  error.value = ''
  try {
    const result = await api.aiModels(aiBaseUrl.value.trim(), aiKey.value.trim())
    modelOptions.value = result.items
    if (!result.items.length) error.value = '网关没有返回任何模型。'
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    loadingModels.value = false
  }
}

async function runScan() {
  error.value = ''
  try {
    await api.startScan({
      name: props.skill.name,
      library: props.skill.library,
      route: route.value,
      ai_base_url: aiBaseUrl.value,
      ai_model: aiModel.value,
      ai_key: aiKey.value,
    })
    wakeJobPolling()
    emit('scanned', { name: props.skill.name, started: true })
    emit('close')
  } catch (requestError) {
    error.value = requestError.message
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open && skill" class="modal-backdrop scan-backdrop" @mousedown.self="emit('close')">
        <section class="modal-panel scan-modal" role="dialog" aria-modal="true" aria-labelledby="scan-title">
          <header class="modal-header">
            <div>
              <span class="step-label">安全闸门</span>
              <h2 id="scan-title">检查 {{ skill.name }}</h2>
            </div>
            <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
              <X :size="20" />
            </button>
          </header>

          <div class="modal-body form-stack">
            <div v-if="!report" class="scan-route-grid">
              <button type="button" class="scan-route" :class="{ selected: route === 'offline' }" @click="route = 'offline'">
                <span class="route-icon"><WifiOff :size="22" /></span>
                <strong>路线 A · 普通检查</strong>
                <p>离线、免费、秒出结果。检查脚本危险动作与 Markdown 提示词注入。</p>
                <span class="route-check"><CheckCircle2 :size="18" /></span>
              </button>
              <button type="button" class="scan-route" :class="{ selected: route === 'ai' }" @click="route = 'ai'">
                <span class="route-icon"><Bot :size="22" /></span>
                <strong>路线 B · AI 深度审查</strong>
                <p>联网、更强、按量计费。使用你自己的 OpenAI 兼容 API。</p>
                <span class="route-check"><CheckCircle2 :size="18" /></span>
              </button>
            </div>

            <div v-if="!report && route === 'ai'" class="ai-fields">
              <label class="field-block ai-preset-field">
                <span>API 供应商预设</span>
                <select v-model="aiProvider" @change="selectAiPreset">
                  <option value="custom">自定义 OpenAI 兼容接口</option>
                  <option v-for="preset in aiPresets" :key="preset.id" :value="preset.id">
                    {{ preset.name }} · {{ preset.model }}
                  </option>
                </select>
              </label>
              <label class="field-block">
                <span>API 地址</span>
                <input v-model="aiBaseUrl" placeholder="https://api.openai.com/v1" />
              </label>
              <label class="field-block">
                <span>模型</span>
                <div class="model-fetch-row">
                  <input
                    v-model="aiModel"
                    list="ai-model-options"
                    placeholder="留空使用网关默认模型"
                  />
                  <datalist id="ai-model-options">
                    <option v-for="m in modelOptions" :key="m" :value="m" />
                  </datalist>
                  <button
                    class="secondary-button fetch-models-button"
                    type="button"
                    :disabled="loadingModels"
                    @click="fetchModels"
                  >
                    <LoaderCircle v-if="loadingModels" class="spinning" :size="15" />
                    {{ loadingModels ? '获取中…' : '获取模型列表' }}
                  </button>
                </div>
                <small v-if="modelOptions.length">网关返回 {{ modelOptions.length }} 个模型，输入时可下拉选择。</small>
              </label>
              <label class="field-block ai-key-field">
                <span>本次 API Key</span>
                <input v-model="aiKey" type="password" :placeholder="config.ai_key_configured ? '已在系统凭据中配置，留空即可' : 'sk-…'" />
                <small>此处输入只用于本次检查，不写入项目文件。</small>
              </label>
            </div>

            <div v-if="report" class="scan-report" :class="`report-${report.status}`">
              <div class="report-summary">
                <span class="report-icon">
                  <ShieldCheck v-if="report.status === 'safe'" :size="24" />
                  <AlertTriangle v-else :size="24" />
                </span>
                <div>
                  <strong>{{ report.status === 'safe' ? '安全无风险' : '发现需要确认的问题' }}</strong>
                  <p>{{ report.summary }}</p>
                </div>
                <span>{{ report.scanned_files }} 个文件</span>
              </div>
              <div v-if="report.findings.length" class="finding-list">
                <article v-for="(finding, index) in report.findings" :key="`${finding.file}-${finding.line}-${index}`" class="finding-row">
                  <span class="severity" :class="`severity-${finding.severity}`">{{ finding.severity }}</span>
                  <div>
                    <strong>{{ finding.rule }}</strong>
                    <p>{{ finding.file }}:{{ finding.line }}</p>
                    <code v-if="finding.excerpt">{{ finding.excerpt }}</code>
                  </div>
                </article>
              </div>
            </div>

            <div v-if="error" class="inline-error" role="alert">
              <AlertTriangle :size="17" />
              <span>{{ error }}</span>
            </div>
          </div>

          <footer class="modal-footer">
            <p class="scan-background-hint">检查将在后台运行，随时可在右下角任务面板查看进度。</p>
            <template v-if="!report">
              <button class="primary-button" type="button" @click="runScan">
                开始检查
              </button>
            </template>
            <template v-else>
              <button
                v-if="report.status === 'warning'"
                class="secondary-button"
                type="button"
                @click="emit('trust', { name: report.name || skill.name })"
              >
                <ShieldCheck :size="16" /> 信任此技能
              </button>
              <button class="primary-button" type="button" @click="emit('close')">完成</button>
            </template>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
