<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  ArchiveRestore, ArrowDownCircle, ArrowUpCircle, Copy, ExternalLink,
  FileWarning, FolderOpen, GitCommitHorizontal, Languages, Pencil, RefreshCw, ShieldCheck, Trash2, X,
} from '@lucide/vue'
import StatusBadge from './StatusBadge.vue'
import TagInput from './TagInput.vue'

const props = defineProps({
  skill: { type: Object, default: null },
  open: { type: Boolean, default: false },
  busyAction: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  tagSuggestions: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'close', 'copy', 'check', 'update', 'scan', 'mode', 'remove', 'open-folder', 'save-tags',
  'save-meta', 'translate', 'trust',
])
const draftTags = ref([])
const editing = ref(false)
const form = reactive({
  name: '',
  dirName: '',
  library: 'skills',
  description: '',
  descriptionZh: '',
  provider: 'github',
  sourceUrl: '',
  version: '',
  licenseName: '',
})

const LIBRARY_OPTIONS = [
  { id: 'skills', label: '共享技能库（所有平台共用）' },
  { id: 'github', label: '程序库（应用程序仓，不挂载 agent）' },
]

const changeCount = computed(() => {
  if (!props.skill?.local_changes) return 0
  return Object.values(props.skill.local_changes).reduce((total, items) => total + items.length, 0)
})
const tagsDirty = computed(() => JSON.stringify(draftTags.value) !== JSON.stringify(props.skill?.tags || []))

const LIBRARY_NAMES = {
  github: '程序库',
  skills: '共享技能库',
  'zcode-skills': 'ZCode 旧分区（待合并）',
  'workbuddy-skills': 'WorkBuddy 旧分区（待合并）',
}
const libraryLabel = computed(() => LIBRARY_NAMES[props.skill?.library] || '')
const displayedDescription = computed(() => props.skill?.description_zh || props.skill?.description || '')

const dirNameError = computed(() => {
  const value = form.dirName.trim()
  if (!value) return '目录名不能为空。'
  if (/[\\/]/.test(value)) return '目录名不能包含 / 或 \\——这里填的是磁盘文件夹名，不是 作者/仓库。'
  if (value.startsWith('.')) return '目录名不能以点开头。'
  return ''
})

// 前端复刻 urltool.parse_source 的核心规则，仅供预览；最终以后端解析为准。
const parsedSource = computed(() => {
  if (form.provider !== 'github') return null
  const raw = form.sourceUrl.trim()
  if (!raw) return null
  const path = raw
    .replace(/^https?:\/\/(www\.)?github\.com\//i, '')
    .replace(/\.git$/i, '')
    .replace(/\/+$/, '')
  const parts = path.split('/').filter(Boolean)
  if (parts.length < 2 || parts.some((part) => !/^[A-Za-z0-9_.-]+$/.test(part))) return null
  const [owner, repo, marker, ref, ...rest] = parts
  const subdir = marker === 'tree' ? rest.join('/') : ''
  return { owner, repo, ref: marker === 'tree' ? (ref || '') : '', subdir }
})

const sourcePreviewText = computed(() => {
  if (form.provider !== 'github') return ''
  if (!form.sourceUrl.trim()) return ''
  if (!parsedSource.value) return '地址无法解析：需要 作者/仓库 或 github.com 完整地址。'
  const { owner, repo, ref, subdir } = parsedSource.value
  return `将解析为：作者 ${owner} · 仓库 ${repo}${ref ? ` · 分支 ${ref}` : ''}${subdir ? ` · 子目录 ${subdir}` : ''}`
})

const formValid = computed(() => (
  !dirNameError.value
  && Boolean(form.name.trim())
  && (form.provider !== 'github' || Boolean(parsedSource.value))
))

function normalizeDirName() {
  if (!parsedSource.value) return
  form.dirName = `${parsedSource.value.owner}__${parsedSource.value.repo}`
}

watch(
  () => [props.skill?.name, props.skill?.tags],
  () => { draftTags.value = [...(props.skill?.tags || [])] },
  { immediate: true, deep: true },
)

watch(
  () => [props.open, props.skill?.name],
  ([open]) => {
    if (open) resetForm()
  },
  { immediate: true },
)

function resetForm() {
  editing.value = false
  const skill = props.skill || {}
  form.name = skill.name || ''
  form.dirName = skill.local_dir ? String(skill.local_dir).split('/').pop() : ''
  form.library = ['skills', 'github'].includes(skill.library) ? skill.library : 'skills'
  form.description = skill.description || ''
  form.descriptionZh = skill.description_zh || ''
  form.provider = skill.provider || 'github'
  form.sourceUrl = skill.source_url || ''
  form.version = skill.version || ''
  form.licenseName = skill.license_name || ''
}

function saveForm() {
  emit('save-meta', props.skill, {
    name: form.name.trim(),
    dir_name: form.dirName.trim(),
    target_library: form.library,
    description: form.description,
    description_zh: form.descriptionZh,
    provider: form.provider,
    source_url: form.provider === 'github' ? form.sourceUrl.trim() : '',
    version: form.version,
    license_name: form.licenseName,
  })
}

function shortHash(value) {
  return value ? value.slice(0, 12) : '未记录'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open && skill" class="drawer-backdrop" @mousedown.self="emit('close')">
        <aside class="detail-drawer" :aria-label="skill.item_type === 'project' ? '应用项目详情' : '技能详情'">
          <header class="drawer-header">
            <div class="drawer-title">
              <span class="drawer-title-source">
                <em
                  class="provider-chip"
                  :class="skill.provider === 'local' ? 'provider-local' : 'provider-github'"
                >{{ skill.provider === 'local' ? '本地自研' : 'GitHub 源' }}</em>
                <span>{{ skill.provider === 'local' ? '自研' : skill.author }}</span>
              </span>
              <h2>{{ skill.name }}</h2>
            </div>
            <button class="icon-button" type="button" aria-label="关闭详情" @click="emit('close')">
              <X :size="20" />
            </button>
          </header>

          <div class="drawer-content">
            <div v-if="loading" class="drawer-loading" role="status" aria-live="polite">
              <span class="loading-spinner" aria-hidden="true"></span>
              <strong>正在读取详细信息</strong>
              <p>先打开工作区，仓库变化和安全信息加载完成后会自动补全。</p>
            </div>
            <template v-else-if="editing">
              <section class="detail-section edit-form-section">
                <div class="detail-section-heading">
                  <div>
                    <h3>编辑信息</h3>
                    <p>修正名字、备注、来源判定或仓库副本目录；保存后立即写入 SQLite 与 index.json。</p>
                  </div>
                </div>
                <div class="edit-form">
                  <label class="edit-field">
                    <span>条目名（身份）</span>
                    <input
                      v-model="form.name"
                      type="text"
                      :disabled="!!busyAction"
                      placeholder="owner/repo，monorepo 子技能含子目录路径"
                    />
                    <small>GitHub 条目 = 作者/仓库[/子目录]；本地自研直接写技能名。与装在哪个库无关，同库内不能重名。</small>
                  </label>
                  <label class="edit-field">
                    <span>仓库副本目录名（归属）</span>
                    <div class="edit-field-inline">
                      <input
                        v-model="form.dirName"
                        type="text"
                        :disabled="!!busyAction"
                        placeholder="磁盘上的实际目录名，如 owner__repo"
                        :class="{ 'input-invalid': dirNameError }"
                      />
                      <button
                        v-if="parsedSource"
                        class="secondary-button normalize-button"
                        type="button"
                        :disabled="!!busyAction"
                        title="按 作者__仓库 规范化目录名"
                        @click="normalizeDirName"
                      >
                        规范化
                      </button>
                    </div>
                    <small v-if="dirNameError" class="field-error">{{ dirNameError }}</small>
                    <small v-else>只决定磁盘位置；改名会同时移动磁盘目录，不影响条目名。</small>
                  </label>
                  <label class="edit-field">
                    <span>所属库（归属）</span>
                    <select v-model="form.library" :disabled="!!busyAction">
                      <option v-for="item in LIBRARY_OPTIONS" :key="item.id" :value="item.id">{{ item.label }}</option>
                    </select>
                    <small>下错了库在这里切换：磁盘目录、记录与 manifest 一起搬到目标库。</small>
                  </label>
                  <label class="edit-field">
                    <span>备注（原生）</span>
                    <textarea v-model="form.description" rows="2" :disabled="!!busyAction" />
                  </label>
                  <label class="edit-field">
                    <span>中文备注</span>
                    <textarea v-model="form.descriptionZh" rows="2" :disabled="!!busyAction" placeholder="可留空，用上方「翻译备注」自动生成" />
                  </label>
                  <label class="edit-field">
                    <span>来源方式</span>
                    <select v-model="form.provider" :disabled="!!busyAction">
                      <option value="github">GitHub 远端（可查版本/更新）</option>
                      <option value="local">本地自研（禁用在线更新）</option>
                    </select>
                  </label>
                  <label v-if="form.provider === 'github'" class="edit-field">
                    <span>来源地址</span>
                    <input
                      v-model="form.sourceUrl"
                      type="text"
                      :disabled="!!busyAction"
                      placeholder="owner/repo，或含 /tree/分支/子目录 的完整 URL"
                    />
                    <small v-if="sourcePreviewText" :class="{ 'field-error': !parsedSource }">{{ sourcePreviewText }}</small>
                    <small v-else>monorepo 子技能请粘贴完整地址（含子目录路径），作者/仓库/子目录会自动解析。</small>
                  </label>
                  <div class="edit-field-row">
                    <label class="edit-field">
                      <span>版本</span>
                      <input v-model="form.version" type="text" :disabled="!!busyAction" />
                    </label>
                    <label class="edit-field">
                      <span>许可证</span>
                      <input v-model="form.licenseName" type="text" :disabled="!!busyAction" />
                    </label>
                  </div>
                </div>
                <div class="edit-form-actions">
                  <button class="secondary-button" type="button" :disabled="!!busyAction" @click="resetForm">
                    取消
                  </button>
                  <button class="primary-button" type="button" :disabled="!!busyAction || !formValid" @click="saveForm">
                    {{ busyAction === 'meta' ? '保存中…' : '保存修改' }}
                  </button>
                </div>
              </section>
            </template>

            <template v-else>
            <div class="detail-description-row">
              <p class="detail-description">{{ displayedDescription }}</p>
              <div class="description-actions">
                <button
                  class="icon-text-button"
                  type="button"
                  :title="skill.description_zh ? '重新翻译备注' : '把备注翻译成中文'"
                  :disabled="!!busyAction"
                  @click="emit('translate', skill)"
                >
                  <Languages :size="14" />
                  <span>{{ busyAction === 'translate' ? '翻译中…' : '翻译备注' }}</span>
                </button>
                <button
                  class="icon-text-button"
                  type="button"
                  title="手动修正名字、备注、来源、版本、仓库副本等信息"
                  :disabled="!!busyAction"
                  @click="editing = true"
                >
                  <Pencil :size="14" />
                  <span>编辑信息</span>
                </button>
              </div>
            </div>
            <div v-if="skill.description_zh && skill.description_zh !== skill.description" class="detail-original-note">
              原生备注：{{ skill.description }}
            </div>
            <div class="detail-status-line">
              <StatusBadge :status="skill.security_status" />
              <span v-if="libraryLabel">{{ libraryLabel }}</span>
              <span>{{ skill.item_type === 'project' ? '应用项目 · Git 克隆' : (skill.install_mode === 'full' ? '全仓安装' : '标准安装') }}</span>
              <span v-if="skill.provider === 'local'">本地自研</span>
              <span v-if="skill.has_scripts">含脚本</span>
              <button
                v-if="skill.security_status === 'warning'"
                class="trust-inline-button"
                type="button"
                @click="emit('trust', skill)"
              >信任此来源</button>
            </div>

            <div class="primary-action-grid">
              <button class="primary-button" type="button" @click="emit('copy', skill)">
                <Copy :size="16" /> {{ skill.item_type === 'project' ? '复制项目使用提示' : '复制技能安装提示词' }}
              </button>
              <button class="secondary-button" type="button" @click="emit('scan', skill)">
                <ShieldCheck :size="16" /> 安全检查
              </button>
            </div>

            <section class="detail-section tag-detail-section">
              <div class="detail-section-heading">
                <div>
                  <h3>分类标签</h3>
                  <p>用于仓库的一键分类筛选，不会修改条目文件。</p>
                </div>
                <button
                  class="secondary-button tag-save-button"
                  type="button"
                  :disabled="!tagsDirty || !!busyAction"
                  @click="emit('save-tags', skill, draftTags)"
                >
                  {{ busyAction === 'tags' ? '保存中…' : '保存标签' }}
                </button>
              </div>
              <TagInput
                v-model="draftTags"
                :suggestions="tagSuggestions"
                :disabled="!!busyAction"
              />
            </section>

            <section class="detail-section">
              <h3>来源与版本</h3>
              <dl class="detail-list">
                <div>
                  <dt>来源</dt>
                  <dd><a :href="skill.source_url" target="_blank" rel="noreferrer">{{ skill.source_url }} <ExternalLink :size="13" /></a></dd>
                </div>
                <div v-if="skill.subdir">
                  <dt>子目录</dt>
                  <dd><code>{{ skill.subdir }}</code></dd>
                </div>
                <div>
                  <dt>当前版本</dt>
                  <dd>{{ skill.version }}</dd>
                </div>
                <div>
                  <dt>Commit</dt>
                  <dd><code>{{ shortHash(skill.commit_hash) }}</code></dd>
                </div>
                <div>
                  <dt>许可证</dt>
                  <dd>{{ skill.license_name || '未识别' }}</dd>
                </div>
                <div>
                  <dt>下载方式</dt>
                  <dd>{{ skill.fetcher === 'archive' ? 'Archive 压缩包' : 'Git 浅克隆' }}</dd>
                </div>
                <div v-if="skill.imported_from">
                  <dt>导入来源</dt>
                  <dd>{{ skill.imported_from }}<small v-if="skill.imported_at"> · {{ String(skill.imported_at).slice(0, 10) }}</small></dd>
                </div>
              </dl>
            </section>

            <section class="detail-section">
              <h3>仓库副本</h3>
              <button class="path-box" type="button" @click="emit('open-folder', skill.absolute_dir)">
                <FolderOpen :size="17" />
                <span>{{ skill.absolute_dir }}</span>
                <ExternalLink :size="13" />
              </button>
              <div v-if="changeCount" class="local-change-note">
                <FileWarning :size="17" />
                <div>
                  <strong>检测到 {{ changeCount }} 项本地变化</strong>
                  <p>更新前会自动备份本地修改，避免覆盖后无法找回。</p>
                </div>
              </div>
              <div v-else class="local-clean-note">
                <GitCommitHorizontal :size="17" />
                <span>仓库副本与 manifest 记录一致</span>
              </div>
            </section>

            <section class="detail-section">
              <h3>维护操作</h3>
              <div class="maintenance-list">
                <button
                  type="button"
                  :disabled="!!busyAction || skill.provider === 'local'"
                  :title="skill.provider === 'local' ? '本地自研技能无在线源头，版本请在「编辑信息」中手动维护' : ''"
                  @click="emit('check', skill)"
                >
                  <GitCommitHorizontal :size="17" />
                  <span><strong>查远端版本</strong><small>{{ skill.provider === 'local' ? '本地自研技能无在线源头' : '只查询 commit，不下载仓库内容' }}</small></span>
                </button>
                <button
                  type="button"
                  :disabled="!!busyAction || skill.provider === 'local'"
                  :title="skill.provider === 'local' ? '本地自研技能无在线源头，版本请在「编辑信息」中手动维护' : ''"
                  @click="emit('update', skill)"
                >
                  <RefreshCw :size="17" :class="{ spinning: busyAction === 'update' }" />
                  <span><strong>更新到最新版本</strong><small>{{ skill.provider === 'local' ? '本地自研技能无在线源头' : '有本地修改时先备份再覆盖' }}</small></span>
                </button>
                <button v-if="skill.item_type !== 'project'" type="button" :disabled="!!busyAction" @click="emit('mode', skill)">
                  <ArrowDownCircle v-if="skill.install_mode === 'full'" :size="17" />
                  <ArrowUpCircle v-else :size="17" />
                  <span>
                    <strong>{{ skill.install_mode === 'full' ? '降级为标准安装' : '升级为全仓安装' }}</strong>
                    <small>{{ skill.install_mode === 'full' ? '只清理未改动的多余文件' : '补齐仓库内所有文件' }}</small>
                  </span>
                </button>
              </div>
            </section>

            <section class="danger-section">
              <h3>危险操作</h3>
              <button class="danger-button" type="button" :disabled="!!busyAction" @click="emit('remove', skill)">
                <Trash2 :size="16" /> {{ skill.item_type === 'project' ? '删除该应用项目' : '删除该技能' }}
              </button>
              <p><ArchiveRestore :size="14" /> 删除后从列表和 index.json 移除，文件移入 `.meta/trash`，可手动恢复。</p>
            </section>
            </template>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>
