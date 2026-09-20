import { reactive } from 'vue'
import { api } from './api'

// 后台任务状态：App 挂载后调用 startJobPolling，任务完成时回调 onFinish(job)。
// dismissed 记录用户手动关闭的任务，轮询时过滤掉，避免服务端仍保留的完成任务反复出现。
export const jobStore = reactive({
  items: [],
  runningCount: 0,
  dismissed: [],
  notified: [],
  timer: null,
})

let finishHandler = null

export function startJobPolling(onFinish) {
  finishHandler = onFinish
  _schedulePolling()
}

// 提交新任务后调用：轮询可能已因“无进行中任务”停止，需要唤醒。
export function wakeJobPolling() {
  if (!jobStore.timer && finishHandler) _schedulePolling()
}

function _schedulePolling() {
  if (jobStore.timer) window.clearTimeout(jobStore.timer)
  const tick = async () => {
    try {
      const data = await api.jobs()
      const dismissed = new Set(jobStore.dismissed)
      jobStore.items = data.items.filter((job) => !dismissed.has(job.id))
      jobStore.runningCount = data.items.filter((job) => job.status === 'running').length
      const notified = new Set(jobStore.notified)
      for (const job of data.items) {
        if ((job.status === 'done' || job.status === 'error') && !notified.has(job.id)) {
          notified.add(job.id)
          finishHandler(job)
        }
      }
      jobStore.notified = [...notified]
      prune(notified)
      if (!jobStore.runningCount) {
        jobStore.timer = null
        return
      }
    } catch {
      // 后端暂时不可达时继续轮询，直到没有进行中的任务
    }
    jobStore.timer = window.setTimeout(tick, 900)
  }
  jobStore.timer = window.setTimeout(tick, 300)
}

export function stopJobPolling() {
  if (jobStore.timer) window.clearTimeout(jobStore.timer)
  jobStore.timer = null
}

export function dismissJob(jobId) {
  // 服务端真删（重开面板/刷新后不再出现）；失败时退回本地过滤兜底
  jobStore.items = jobStore.items.filter((job) => job.id !== jobId)
  api.dismissJob(jobId).catch(() => {
    jobStore.dismissed.push(jobId)
  })
}

export function clearFinishedJobs() {
  const finished = jobStore.items.filter((job) => job.status !== 'running')
  jobStore.items = jobStore.items.filter((job) => job.status === 'running')
  api.clearFinishedJobs().catch(() => {
    for (const job of finished) jobStore.dismissed.push(job.id)
  })
}

function prune(notified) {
  const alive = new Set(jobStore.items.map((job) => job.id))
  jobStore.dismissed = jobStore.dismissed.filter((id) => alive.has(id))
  jobStore.notified = [...notified].filter((id) => alive.has(id) || jobStore.dismissed.includes(id))
    .filter((id) => alive.has(id))
}
