<script setup>
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle, AppWindow, ArrowLeft, Check, ChevronDown, FileCode2, FolderGit2,
  LoaderCircle, X,
} from '@lucide/vue'
import { api } from '../api'
import { buildRepositoryRequest } from '../repositoryMode.js'
import { wakeJobPolling } from '../jobStore'
import TagInput from './TagInput.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  tagSuggestions: { type: Array, default: () => [] },
  libraries: { type: Array, default: () => [] },
  multiLibrary: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'toast'])

const source = ref('')
const itemType = ref('skill')
const mode = ref('standard')
const fetcher = ref('archive')
const refName = ref('')
const subdir = ref('')
const library = ref('skills')
const showAdvanced = ref(false)
const loading = ref(false)
const error = ref('')
const preview = ref(null)
const selectedFiles = ref([])
const fileFilter = ref('')
const tags = ref([])

const filteredFiles = computed(() => {
  const term = fileFilter.value.trim().toLowerCase()
  if (!term) return preview.value?.files || []
  return preview.value?.files.filter((file) => file.toLowerCase().includes(term)) || []
})

const selectedSize = computed(() => selectedFiles.value.length)
const allVisibleSelected = computed(() => (
  filteredFiles.value.length > 0
  && filteredFiles.value.every((file) => selectedFiles.value.includes(file))
))

watch(() => props.open, (value) => {
  if (value) reset()
})

// 技能默认进共享技能库，应用程序项目默认进程序库（仍可手动改）
watch(itemType, (value) => {
  library.value = value === 'project' ? 'github' : 'skills'
})

function reset() {
  source.value = ''
  itemType.value = 'skill'
  mode.value = 'standard'
  fetcher.value = 'archive'
  refName.value = ''
  subdir.value = ''
  library.value = 'skills'
  showAdvanced.value = false
  error.value = ''
  preview.value = null
  selectedFiles.value = []
  fileFilter.value = ''
  tags.value = []
}

function payload() {
  return buildRepositoryRequest({
    source: source.value.trim(),
    item_type: itemType.value,
    mode: mode.value,
    fetcher: fetcher.value,
    ref: refName.value,
    subdir: subdir.value,
    library: props.multiLibrary ? library.value : null,
  })
}

async function loadPreview() {
  if (!source.value.trim()) {
    error.value = '请输入 GitHub 地址或“作者/仓库”。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    preview.value = await api.preview(payload())
    mode.value = preview.value.mode
    fetcher.value = preview.value.fetcher
    selectedFiles.value = [...preview.value.files]
    applyRecognition()
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    loading.value = false
  }
}

// 按仓库内容自动识别技能/程序并切换（用户仍可手动改）
function applyRecognition() {
  const suggested = preview.value?.suggested_item_type
  if (!suggested) return
  itemType.value = suggested
}

const recognition = computed(() => preview.value?.suggested_item_type
  ? {
      type: preview.value.suggested_item_type,
      reason: preview.value.suggestion_reason || '',
      subdirs: preview.value.skill_subdirs || [],
    }
  : null)

function useSubdir(dir) {
  subdir.value = dir
  showAdvanced.value = true
  loadPreview()
}

async function install() {
  error.value = ''
  try {
    await api.startInstall({
      ...payload(),
      overwrite: Boolean(preview.value?.exists),
      selected_files: itemType.value === 'skill' && mode.value === 'standard' ? selectedFiles.value : null,
      tags: tags.value,
    })
    wakeJobPolling()
    emit('close')
    emit('toast', {
      type: 'success',
      message: `${preview.value?.name || source.value.trim()} 已转入后台下载，进度见右下角任务面板。`,
    })
  } catch (requestError) {
    error.value = requestError.message
  }
}

function toggleFile(file) {
  selectedFiles.value = selectedFiles.value.includes(file)
    ? selectedFiles.value.filter((item) => item !== file)
    : [...selectedFiles.value, file]
}

function toggleVisible() {
  if (allVisibleSelected.value) {
    const visible = new Set(filteredFiles.value)
    selectedFiles.value = selectedFiles.value.filter((file) => !visible.has(file))
  } else {
    selectedFiles.value = [...new Set([...selectedFiles.value, ...filteredFiles.value])]
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @mousedown.self="emit('close')">
        <section class="modal-panel add-modal" role="dialog" aria-modal="true" aria-labelledby="add-title">
          <header class="modal-header">
            <div>
              <span class="step-label">{{ preview ? '第 2 步，共 2 步' : '第 1 步，共 2 步' }}</span>
              <h2 id="add-title">{{ preview ? '确认入库内容' : '添加技能或应用项目' }}</h2>
            </div>
            <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
              <X :size="20" />
            </button>
          </header>

          <div v-if="!preview" class="modal-body form-stack">
            <label class="field-block">
              <span>仓库地址</span>
              <input
                v-model="source"
                autofocus
                autocomplete="off"
                placeholder="anthropics/skills 或完整 GitHub URL"
                @keydown.enter="loadPreview"
              />
              <small>支持 `作者/仓库` 和 `/tree/分支/子目录` 地址。</small>
            </label>

            <fieldset class="choice-fieldset repository-type-fieldset">
              <legend>内容类型</legend>
              <label class="choice-row" :class="{ selected: itemType === 'skill' }">
                <input v-model="itemType" type="radio" value="skill" />
                <span class="choice-control"><Check :size="14" /></span>
                <span>
                  <strong>Agent 技能</strong>
                  <small>识别 SKILL.md，可选择标准安装或全仓安装</small>
                </span>
              </label>
              <label class="choice-row" :class="{ selected: itemType === 'project' }">
                <input v-model="itemType" type="radio" value="project" />
                <span class="choice-control"><Check :size="14" /></span>
                <span>
                  <strong>应用程序项目克隆</strong>
                  <small>保留完整 Git 仓库，用于溯源、版本检查和随时升级</small>
                </span>
              </label>
            </fieldset>

            <div v-if="recognition" class="recognition-note" :class="`recognition-${recognition.type}`">
              <span class="recognition-tag">{{ recognition.type === 'skill' ? '已识别为技能' : '已识别为程序' }}</span>
              <small>{{ recognition.reason }}</small>
              <div v-if="recognition.subdirs.length" class="recognition-subdirs">
                <button
                  v-for="dir in recognition.subdirs.slice(0, 6)"
                  :key="dir"
                  type="button"
                  @click="useSubdir(dir)"
                >{{ dir }}</button>
                <span v-if="recognition.subdirs.length > 6">等 {{ recognition.subdirs.length }} 个</span>
              </div>
            </div>

            <div v-if="itemType === 'project'" class="project-clone-note">
              <AppWindow :size="18" />
              <div>
                <strong>项目模式需要系统已安装 Git</strong>
                <p>将自动使用 Git 浅克隆、保留 `.git`，并完整保存安装文件；不能选择仓库子目录。</p>
              </div>
            </div>

            <label v-if="multiLibrary" class="field-block">
              <span>入库到技能库</span>
              <select v-model="library">
                <option v-for="item in libraries" :key="item.id" :value="item.id">{{ item.label }}</option>
              </select>
              <small>共享技能库对全部 agent 生效；程序库存放应用程序仓，不挂载给 agent。</small>
            </label>

            <div class="field-block">
              <span>分类标签 <b class="optional-label">可选</b></span>
              <TagInput v-model="tags" :suggestions="tagSuggestions" />
            </div>

            <fieldset v-if="itemType === 'skill'" class="choice-fieldset">
              <legend>安装模式</legend>
              <label class="choice-row" :class="{ selected: mode === 'standard' }">
                <input v-model="mode" type="radio" value="standard" />
                <span class="choice-control"><Check :size="14" /></span>
                <span>
                  <strong>标准安装</strong>
                  <small>SKILL.md 与它引用的脚本、资源，默认推荐</small>
                </span>
              </label>
              <label class="choice-row" :class="{ selected: mode === 'full' }">
                <input v-model="mode" type="radio" value="full" />
                <span class="choice-control"><Check :size="14" /></span>
                <span>
                  <strong>全仓安装</strong>
                  <small>整个技能目录完整保留，适合高频或重资源技能</small>
                </span>
              </label>
            </fieldset>

            <button class="advanced-toggle" type="button" @click="showAdvanced = !showAdvanced">
              高级选项
              <ChevronDown :size="16" :class="{ expanded: showAdvanced }" />
            </button>
            <div v-if="showAdvanced" class="advanced-grid">
              <label v-if="itemType === 'skill'" class="field-block">
                <span>下载方式</span>
                <select v-model="fetcher">
                  <option value="archive">Archive 压缩包（推荐）</option>
                  <option value="git">Git 浅克隆</option>
                </select>
              </label>
              <label class="field-block">
                <span>分支或 Ref</span>
                <input v-model="refName" placeholder="默认 HEAD" />
              </label>
              <label v-if="itemType === 'skill'" class="field-block advanced-wide">
                <span>仓库内子目录</span>
                <input v-model="subdir" placeholder="例如 skills/pdf（URL 已含时无需填写）" />
              </label>
            </div>

            <div v-if="error" class="inline-error" role="alert">
              <AlertTriangle :size="17" />
              <span>{{ error }}</span>
            </div>
          </div>

          <div v-else class="modal-body preview-body">
            <div class="preview-summary">
              <div class="repo-mark"><FolderGit2 :size="23" /></div>
              <div>
                <strong>{{ preview.name }}</strong>
                <span class="preview-type-label">{{ preview.item_type === 'project' ? '应用项目' : 'Agent 技能' }}</span>
                <p>{{ preview.description }}</p>
              </div>
              <dl>
                <div><dt>版本</dt><dd>{{ preview.version }}</dd></div>
                <div><dt>文件</dt><dd>{{ selectedSize }} / {{ preview.all_file_count }}</dd></div>
                <div><dt>体积</dt><dd>{{ formatBytes(preview.total_bytes) }}</dd></div>
              </dl>
            </div>
            <div v-if="tags.length" class="preview-tags">
              <span>分类</span>
              <b v-for="tag in tags" :key="tag">#{{ tag }}</b>
            </div>

            <div v-if="preview.exists" class="inline-warning">
              <AlertTriangle :size="17" />
              <span>同一仓库已存在。继续后将先保护本地改动，再覆盖仓库副本。</span>
            </div>
            <div v-if="preview.size_warning" class="inline-warning">
              <AlertTriangle :size="17" />
              <span>安装内容超过 100MB，请确认这是预期的资源规模。</span>
            </div>
            <div v-for="warning in preview.warnings" :key="warning" class="inline-warning">
              <AlertTriangle :size="17" />
              <span>{{ warning }}</span>
            </div>

            <section class="file-review">
              <div class="file-review-header">
                <div>
                  <h3>文件清单</h3>
                  <p>{{ preview.item_type === 'project' ? '项目模式保留完整仓库及 Git 溯源信息。' : (mode === 'standard' ? '解析结果只是建议，你可以在入库前调整。' : '全仓模式将保留全部文件。') }}</p>
                </div>
                <input v-model="fileFilter" class="file-search" placeholder="筛选文件" />
              </div>
              <label v-if="mode === 'standard'" class="select-all-row">
                <input type="checkbox" :checked="allVisibleSelected" @change="toggleVisible" />
                <span>选择当前 {{ filteredFiles.length }} 个文件</span>
              </label>
              <div class="file-list">
                <label v-for="file in filteredFiles" :key="file" class="file-row">
                  <input
                    v-if="mode === 'standard'"
                    type="checkbox"
                    :checked="selectedFiles.includes(file)"
                    @change="toggleFile(file)"
                  />
                  <FileCode2 :size="15" />
                  <span>{{ file }}</span>
                </label>
                <p v-if="filteredFiles.length === 0" class="no-file-result">没有匹配的文件</p>
              </div>
            </section>

            <div v-if="error" class="inline-error" role="alert">
              <AlertTriangle :size="17" />
              <span>{{ error }}</span>
            </div>
          </div>

          <footer class="modal-footer">
            <button
              v-if="preview"
              class="secondary-button"
              type="button"
              @click="preview = null; error = ''"
            >
              <ArrowLeft :size="16" /> 返回修改
            </button>
            <span v-else></span>
            <button
              v-if="!preview"
              class="primary-button"
              type="button"
              :disabled="loading || !source.trim()"
              @click="loadPreview"
            >
              <LoaderCircle v-if="loading" class="spinning" :size="17" />
              {{ loading ? '正在读取仓库…' : '预览文件清单' }}
            </button>
            <button
              v-else
              class="primary-button"
              type="button"
              :disabled="mode === 'standard' && selectedSize === 0"
              @click="install"
            >
              {{ preview.exists ? '确认覆盖入库' : (itemType === 'project' ? '确认克隆项目' : '确认入库') }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
