<script setup>
import { computed, ref } from 'vue'
import {
  CheckCircle2, ChevronDown, CircleAlert, Download, ListChecks, RefreshCw, ShieldCheck, X,
} from '@lucide/vue'
import { clearFinishedJobs, dismissJob, jobStore } from '../jobStore'

const emit = defineEmits(['view-scan'])
const collapsed = ref(false)

const hasItems = computed(() => jobStore.items.length > 0)
const hasFinished = computed(() => jobStore.items.some((job) => job.status !== 'running'))

const kindConfig = {
  install: { icon: Download, label: '入库' },
  update: { icon: RefreshCw, label: '更新' },
  scan: { icon: ShieldCheck, label: '安全检查' },
}

function kindIcon(kind) {
  return kindConfig[kind]?.icon || ListChecks
}

function kindText(kind) {
  return kindConfig[kind]?.label || '任务'
}

// 后台任务时间戳：本地时间 MM-DD HH:MM:SS，一眼分清先后
function jobTime(job) {
  if (!job.created_at) return ''
  const date = new Date(job.created_at)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function resultLine(job) {
  if (job.status === 'running') return job.detail || job.phase
  if (job.status === 'error') return job.error || '任务失败'
  if (job.kind === 'scan') {
    return job.result?.status === 'safe' ? '检查完成：安全无风险' : `检查完成：${job.result?.summary || '发现需要确认的问题'}`
  }
  if (job.kind === 'update') return job.result?.updated ? '已更新到最新版本' : '已是最新版本'
  return job.result?.security_status === 'warning' ? '已入库，安全检查发现需确认的问题' : '已安全入库'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="task-panel">
      <button
        v-if="collapsed && hasItems"
        class="task-fab"
        type="button"
        :aria-label="`展开后台任务（${jobStore.runningCount} 个进行中）`"
        @click="collapsed = false"
      >
        <ListChecks :size="17" />
        <span>{{ jobStore.runningCount ? `${jobStore.runningCount} 个任务进行中` : '后台任务' }}</span>
        <b v-if="jobStore.runningCount"></b>
      </button>

      <section v-else-if="hasItems" class="task-panel" role="region" aria-label="后台任务">
        <header class="task-panel-header">
          <div class="task-panel-title">
            <ListChecks :size="17" />
            <strong>后台任务</strong>
            <b v-if="jobStore.runningCount">{{ jobStore.runningCount }} 个进行中</b>
          </div>
          <div class="task-panel-actions">
            <button
              v-if="hasFinished"
              class="task-clear"
              type="button"
              @click="clearFinishedJobs"
            >清除已完成</button>
            <button
              class="icon-button task-collapse"
              type="button"
              aria-label="收起面板"
              @click="collapsed = true"
            >
              <ChevronDown :size="18" />
            </button>
          </div>
        </header>

        <div class="task-panel-list">
          <article v-for="job in jobStore.items" :key="job.id" class="task-item" :class="`task-${job.status}`">
            <span class="task-kind-icon">
              <component :is="kindIcon(job.kind)" :size="16" :class="{ spinning: job.status === 'running' }" />
            </span>
            <div class="task-item-body">
              <div class="task-item-top">
                <strong>{{ job.label }}</strong>
                <span class="task-kind-tag">{{ kindText(job.kind) }}</span>
                <span class="task-time-tag" :title="job.created_at">{{ jobTime(job) }}</span>
              </div>
              <div v-if="job.status === 'running'" class="task-progress">
                <div class="task-progress-track">
                  <i v-if="job.progress === null" class="indeterminate"></i>
                  <i v-else :style="{ width: `${job.progress}%` }"></i>
                </div>
                <p>{{ job.phase }}<template v-if="job.detail"> · {{ job.detail }}</template></p>
              </div>
              <p v-else class="task-result-line" :class="{ 'task-error-line': job.status === 'error' }">
                <CheckCircle2 v-if="job.status === 'done'" :size="14" />
                <CircleAlert v-else :size="14" />
                {{ resultLine(job) }}
              </p>
              <div v-if="job.status === 'done' && job.kind === 'scan'" class="task-item-actions">
                <button class="secondary-button task-view-report" type="button" @click="emit('view-scan', job)">
                  查看检查结果
                </button>
              </div>
            </div>
            <button
              v-if="job.status !== 'running'"
              class="icon-button task-dismiss"
              type="button"
              aria-label="关闭此任务"
              @click="dismissJob(job.id)"
            >
              <X :size="15" />
            </button>
          </article>
        </div>
      </section>
    </Transition>
  </Teleport>
</template>
