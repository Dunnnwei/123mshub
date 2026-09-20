<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle, CheckCircle2, ChevronDown, ClipboardList, Database, FolderSearch, PackagePlus, X,
} from '@lucide/vue'
import { api } from '../api'

/**
 * 导入记忆技能库：扫描预览 → 确认 → 后台导入（进度实时刷新）→ 结果报告。
 * 关闭弹窗不中断后台任务（JobManager 串行执行，任务面板可再看结果）。
 */
const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'toast', 'finished'])

const stage = ref('idle') // idle | picking | scanning | preview | importing | done
const sourcePath = ref('')
const manualPath = ref('')
const includeMemory = ref(true)
const includeSkills = ref(true)
const progressPercent = ref(0)
const progressPhase = ref('')
const progressDetail = ref('')
const preview = ref(null)
const result = ref(null)
const showDetail = ref(false)
let pollTimer = null

const busy = computed(() => stage.value === 'scanning' || stage.value === 'importing')

function reset() {
  stage.value = 'idle'
  sourcePath.value = ''
  manualPath.value = ''
  preview.value = null
  result.value = null
  showDetail.value = false
  progressPercent.value = 0
  progressPhase.value = ''
  progressDetail.value = ''
  includeMemory.value = true
  includeSkills.value = true
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(stopPolling)

// 组件常驻渲染（无 v-if）：每次打开都从初始界面开始，不残留上一次的预览/结果
watch(() => props.open, (open) => {
  if (open) reset()
})

function close() {
  if (busy.value) {
    // 后台任务继续跑：任务面板与完成 toast 不丢
    emit('toast', { type: 'info', message: '导入任务已转后台继续执行，可在右下角任务面板查看进度。' })
  }
  stopPolling()
  emit('close')
}

async function chooseFolder() {
  stage.value = 'picking'
  try {
    const picked = await api.selectImportDirectory()
    if (!picked.path) {
      stage.value = 'idle'
      return
    }
    sourcePath.value = picked.path
    await startScan()
  } catch (error) {
    stage.value = 'idle'
    emit('toast', { type: 'error', message: error.message })
  }
}

async function startScan() {
  stage.value = 'scanning'
  progressPercent.value = 0
  progressPhase.value = '正在扫描来源目录'
  try {
    const submitted = await api.migrationScan(sourcePath.value)
    pollJob(submitted.job_id, (job) => {
      preview.value = job.result
      stage.value = 'preview'
    })
  } catch (error) {
    stage.value = 'idle'
    emit('toast', { type: 'error', message: error.message })
  }
}

function startManualScan() {
  const value = manualPath.value.trim()
  if (!value) return
  sourcePath.value = value
  startScan()
}

function pollJob(jobId, onDone) {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const data = await api.jobs()
      const job = data.items.find((item) => item.id === jobId)
      if (!job) return
      if (job.progress != null) progressPercent.value = job.progress
      if (job.phase) progressPhase.value = job.phase
      if (job.detail) progressDetail.value = job.detail
      if (job.status === 'error') {
        stopPolling()
        stage.value = 'idle'
        emit('toast', { type: 'error', message: `${job.label} 失败：${job.error}` })
        return
      }
      if (job.status === 'done') {
        stopPolling()
        onDone(job)
      }
    } catch {
      /* 轮询失败继续等下一拍 */
    }
  }, 400)
}

async function startImport() {
  stage.value = 'importing'
  progressPercent.value = 0
  progressPhase.value = '正在准备导入'
  try {
    const submitted = await api.migrationRun(sourcePath.value, {
      includeMemory: includeMemory.value,
      includeSkills: includeSkills.value,
    })
    pollJob(submitted.job_id, (job) => {
      result.value = job.result
      stage.value = 'done'
      emit('finished')
      emit('toast', {
        type: 'success',
        message: `导入完成：记忆 +${job.result.memory_imported}，技能 +${job.result.skills_imported.length}。整理日报已生成。`,
      })
    })
  } catch (error) {
    stage.value = 'preview'
    emit('toast', { type: 'error', message: error.message })
  }
}

const previewSummary = computed(() => {
  if (!preview.value) return []
  const rows = [
    { icon: 'memory', label: '记忆条目', count: preview.value.memory_count, hint: '导入到记忆库 notes\\（重名自动避让）' },
    { icon: 'skill', label: '技能 / 项目', count: preview.value.skill_count, hint: '复制进技能库与程序库，自动入册' },
  ]
  return rows
})

const resultLines = computed(() => {
  if (!result.value) return []
  const lines = []
  lines.push(`记忆：导入 ${result.value.memory_imported} 条`
    + (result.value.memory_renamed.length ? `，重名避让 ${result.value.memory_renamed.length} 条` : '')
    + (result.value.memory_skipped_same.length ? `，内容相同跳过 ${result.value.memory_skipped_same.length} 条` : '')
    + (result.value.memory_failed.length ? `，失败 ${result.value.memory_failed.length} 条` : ''))
  lines.push(`技能：导入 ${result.value.skills_imported.length} 个`
    + (result.value.skills_skipped.length ? `，跳过 ${result.value.skills_skipped.length} 个` : '')
    + (result.value.skills_failed.length ? `，失败 ${result.value.skills_failed.length} 个` : ''))
  lines.push(`入库后总计：记忆 ${result.value.memory_count} 条 / 技能 ${result.value.skill_count} 个`)
  if (result.value.duplicate_groups?.length) {
    lines.push(`疑似重复 ${result.value.duplicate_groups.length} 组（标题归一化相同，建议在记忆库里人工合并）`)
  }
  return lines
})

const resultDetail = computed(() => {
  if (!result.value) return []
  const detail = []
  if (result.value.memory_renamed?.length) detail.push('重名避让：' + result.value.memory_renamed.join('；'))
  if (result.value.skills_skipped?.length) detail.push('技能跳过：' + result.value.skills_skipped.join('；'))
  if (result.value.skills_failed?.length) detail.push('技能失败：' + result.value.skills_failed.join('；'))
  if (result.value.memory_failed?.length) detail.push('记忆失败：' + result.value.memory_failed.join('；'))
  if (result.value.errors?.length) detail.push('整理步骤异常：' + result.value.errors.join('；'))
  return detail
})
</script>

<template>
  <div v-if="open" class="modal-backdrop" @click.self="!busy && close()">
    <section class="import-modal" role="dialog" aria-label="导入记忆技能库">
      <header class="import-modal-head">
        <div>
          <h2><Database :size="18" /> 导入记忆技能库</h2>
          <p>从任意目录打捞可识别的记忆与技能：支持 123mshub 仓库、DSH 总机（brain + memory.md）、
            Engramory 式索引，以及其他 agent 目录里的散装记忆；认不出的内容会跳过，不会误收。</p>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" :disabled="false" @click="close">
          <X :size="18" />
        </button>
      </header>

      <div class="import-modal-body">
        <!-- 第一步：选择目录 -->
        <template v-if="stage === 'idle' || stage === 'picking'">
          <div class="import-start">
            <button class="primary-button" type="button" :disabled="stage === 'picking'" @click="chooseFolder">
              <FolderSearch :size="17" /> {{ stage === 'picking' ? '等待选择目录…' : '选择要导入的目录' }}
            </button>
            <p class="import-hint">
              导入包含整理步骤（写入、复制、入册、去重审查、重建索引、生成整理日报），
              大目录会花一些时间——全程后台执行，关掉这个窗口也不中断。
            </p>
            <div class="import-manual-path">
              <span>或直接输入路径：</span>
              <input
                v-model="manualPath"
                type="text"
                placeholder="D:\DSH 或任意 agent 的工作目录"
                spellcheck="false"
                @keydown.enter="startManualScan"
              />
              <button class="secondary-button" type="button" :disabled="!manualPath.trim()" @click="startManualScan">
                扫描
              </button>
            </div>
          </div>
        </template>

        <!-- 扫描中 -->
        <template v-else-if="stage === 'scanning'">
          <div class="import-progress">
            <p class="import-source">{{ sourcePath }}</p>
            <div class="progress-track"><div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div></div>
            <p class="progress-caption">{{ progressPhase }} <span v-if="progressDetail">· {{ progressDetail }}</span></p>
          </div>
        </template>

        <!-- 预览确认 -->
        <template v-else-if="stage === 'preview'">
          <p class="import-source">{{ sourcePath }}<span v-if="preview.scanned_files"> · 扫描了 {{ preview.scanned_files }} 个 md 文件</span></p>
          <div v-if="!preview.memory_count && !preview.skill_count" class="import-empty">
            <AlertTriangle :size="18" />
            <p>这个目录里没有识别出可导入的记忆或技能。<br />
              支持：123mshub 仓库、DSH 总机格式（memory.md + brain\）、Engramory 式索引、
              带 frontmatter 的散装记忆 md、含 SKILL.md 的技能目录。</p>
          </div>
          <template v-else>
            <div class="import-summary-row">
              <div v-for="row in previewSummary" :key="row.label" class="import-summary-card">
                <component :is="row.icon === 'memory' ? ClipboardList : PackagePlus" :size="18" />
                <div>
                  <strong>{{ row.count }}</strong>
                  <span>{{ row.label }}</span>
                  <small>{{ row.hint }}</small>
                </div>
              </div>
            </div>
            <div class="import-options">
              <label><input v-model="includeMemory" type="checkbox" /> 导入记忆（{{ preview.memory_count }} 条）</label>
              <label><input v-model="includeSkills" type="checkbox" /> 导入技能（{{ preview.skill_count }} 个）</label>
            </div>
            <details v-if="preview.memory_preview.length || preview.skill_preview.length" class="import-preview-list">
              <summary>查看识别明细</summary>
              <ul>
                <li v-for="item in preview.memory_preview" :key="`m-${item.file}-${item.name}`">
                  <b :class="`kind-${item.kind}`">{{ item.kind }}</b>
                  {{ item.title || item.name }}<small v-if="item.description"> — {{ item.description }}</small>
                </li>
                <li v-for="item in preview.skill_preview" :key="`s-${item.dir}`">
                  <b :class="`kind-${item.kind}`">{{ item.kind }}</b>
                  {{ item.name }}<small>（{{ item.library }} / {{ item.dir }}）</small>
                </li>
              </ul>
            </details>
            <p v-for="note in preview.notes" :key="note" class="import-note">{{ note }}</p>
          </template>
        </template>

        <!-- 导入中 -->
        <template v-else-if="stage === 'importing'">
          <div class="import-progress">
            <p class="import-source">{{ sourcePath }}</p>
            <div class="progress-track"><div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div></div>
            <p class="progress-caption">{{ progressPhase }} <span v-if="progressDetail">· {{ progressDetail }}</span></p>
            <p class="import-hint">整理步骤（去重审查、入册、重建索引、生成日报）正在后台执行，关闭窗口不中断。</p>
          </div>
        </template>

        <!-- 完成 -->
        <template v-else-if="stage === 'done' && result">
          <div class="import-result">
            <div class="import-result-head">
              <CheckCircle2 :size="22" />
              <div>
                <h3>导入完成</h3>
                <p v-for="line in resultLines" :key="line">{{ line }}</p>
              </div>
            </div>
            <details v-if="resultDetail.length" class="import-preview-list">
              <summary @click.prevent="showDetail = !showDetail">
                <ChevronDown :size="14" :class="{ open: showDetail }" /> 处理明细（{{ resultDetail.length }}）
              </summary>
              <ul>
                <li v-for="line in resultDetail" :key="line">{{ line }}</li>
              </ul>
            </details>
            <p v-if="result.tidy_report" class="import-note">
              导入后的库况已写入整理日报（{{ result.tidy_report.file }}），可在记忆库页「整理日报」查看完整内容。
            </p>
          </div>
        </template>
      </div>

      <footer class="import-modal-actions">
        <span class="drawer-actions-spacer"></span>
        <button v-if="stage === 'preview' && (preview.memory_count || preview.skill_count)" class="secondary-button" type="button" @click="close">取消</button>
        <button
          v-if="stage === 'preview' && (preview.memory_count || preview.skill_count)"
          class="primary-button"
          type="button"
          :disabled="!includeMemory && !includeSkills"
          @click="startImport"
        ><PackagePlus :size="15" /> 开始导入</button>
        <button v-if="stage === 'done'" class="primary-button" type="button" @click="reset">再导入一个目录</button>
      </footer>
    </section>
  </div>
</template>
