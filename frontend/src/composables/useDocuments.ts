// 文档与长任务状态（模块级单例）：上传/删除的 job 轮询属于业务状态，跨组件卸载仍在跑，
// 组件卸载不该丢掉进度（`docs/refactor/10` F3）。
import { reactive, ref } from "vue"
import * as api from "../api/client"
import { describeError } from "../utils/errors"
import type { DocumentInfo, JobStep, JobStepStatus } from "../api/types"

/** 步骤的视图模型：label 由后端给或留空，展示文案一律由组件按 key 走 i18n（R9） */
export interface StepView {
  key: string
  label: string
  percent: number
  status: JobStepStatus
  message: string
}

export interface DeleteJobView {
  jobId: string
  status: JobStepStatus
  message: string
  error: string
  collapsed: boolean
  steps: StepView[]
}

// 只登记 key：中文串留在 i18n，状态层不持有展示文案
const UPLOAD_STEP_KEYS = ["upload", "cleanup", "parse", "parent_store", "vector_store"] as const
const DELETE_STEP_KEYS = ["prepare", "bm25", "milvus", "parent_store"] as const
const POLL_INTERVAL_MS = 1000
/** 删除完成后列表项停留的时间：让"已完成"状态可见，再让位给刷新结果 */
const REMOVE_AFTER_MS = 3000

const documents = ref<DocumentInfo[]>([])
const isLoading = ref(false)
const selectedFile = ref<File | null>(null)
const isUploading = ref(false)
const uploadSteps = ref<StepView[]>([])
const uploadMessage = ref("")
const uploadError = ref("")
const uploadCollapsed = ref(false)
const deleteJobs = reactive<Record<string, DeleteJobView>>({})

let uploadTimer: ReturnType<typeof setInterval> | null = null
const deleteTimers: Record<string, ReturnType<typeof setInterval>> = {}
const removeTimers: Record<string, ReturnType<typeof setTimeout>> = {}

function blankSteps(keys: readonly string[]): StepView[] {
  return keys.map((key) => ({ key, label: "", percent: 0, status: "pending", message: "" }))
}

function toSteps(steps: JobStep[] | undefined, fallbackKeys: readonly string[]): StepView[] {
  if (!Array.isArray(steps)) return blankSteps(fallbackKeys)
  return steps.map((step) => ({
    key: step.key,
    label: step.label || "",
    percent: Math.max(0, Math.min(100, step.percent)),
    status: step.status,
    message: step.message || "",
  }))
}

function updateStep(key: string, percent: number, status: JobStepStatus): void {
  if (!uploadSteps.value.length) uploadSteps.value = blankSteps(UPLOAD_STEP_KEYS)
  const idx = uploadSteps.value.findIndex((s) => s.key === key)
  if (idx === -1) return
  uploadSteps.value[idx] = { ...uploadSteps.value[idx], percent: Math.max(0, Math.min(100, percent)), status }
}

/** 删除中的文档还没从后端消失，直接覆盖列表会让它"闪回来"，所以保留本地那一份 */
function mergeWithPendingDelete(next: DocumentInfo[]): DocumentInfo[] {
  const deleting = Object.keys(deleteJobs)
  if (!deleting.length) return next
  const merged = [...next]
  for (const filename of deleting) {
    if (!merged.some((d) => d.filename === filename)) {
      const current = documents.value.find((d) => d.filename === filename)
      if (current) merged.push(current)
    }
  }
  return merged
}

function stopUploadPoll(): void {
  if (uploadTimer) {
    clearInterval(uploadTimer)
    uploadTimer = null
  }
}

function stopDeletePoll(filename: string): void {
  const timer = deleteTimers[filename]
  if (timer) {
    clearInterval(timer)
    delete deleteTimers[filename]
  }
}

function clearRemoveTimer(filename: string): void {
  const timer = removeTimers[filename]
  if (timer) {
    clearTimeout(timer)
    delete removeTimers[filename]
  }
}

export function useDocuments() {
  async function refresh(): Promise<void> {
    isLoading.value = true
    try {
      const data = await api.listDocuments()
      documents.value = mergeWithPendingDelete(data.documents || [])
    } finally {
      isLoading.value = false
    }
  }

  function selectFile(file: File | null): void {
    selectedFile.value = file
    uploadMessage.value = ""
    uploadError.value = ""
    uploadSteps.value = []
    uploadCollapsed.value = false
  }

  function startUploadPoll(jobId: string): void {
    stopUploadPoll()
    const tick = async (): Promise<void> => {
      try {
        const job = await api.getUploadJob(jobId)
        uploadMessage.value = job.message || ""
        uploadSteps.value = toSteps(job.steps, UPLOAD_STEP_KEYS)
        if (job.status === "completed") uploadCollapsed.value = true
        if (job.status === "completed" || job.status === "failed") {
          stopUploadPoll()
          isUploading.value = false
          if (job.status === "completed") {
            selectedFile.value = null
            await refresh()
          }
        }
      } catch (err: unknown) {
        stopUploadPoll()
        isUploading.value = false
        uploadError.value = describeError(err)
      }
    }
    void tick()
    uploadTimer = setInterval(() => void tick(), POLL_INTERVAL_MS)
  }

  async function upload(): Promise<void> {
    const file = selectedFile.value
    if (!file || isUploading.value) return
    isUploading.value = true
    uploadError.value = ""
    uploadMessage.value = ""
    uploadCollapsed.value = false
    uploadSteps.value = blankSteps(UPLOAD_STEP_KEYS)
    try {
      const job = await api.startUploadJob(file, (percent) => updateStep("upload", percent, "running"))
      updateStep("upload", 100, "completed")
      uploadMessage.value = job.message
      startUploadPoll(job.job_id)
    } catch (err: unknown) {
      updateStep("upload", 100, "failed")
      uploadError.value = describeError(err)
      isUploading.value = false
    }
  }

  function startDeletePoll(filename: string, jobId: string): void {
    stopDeletePoll(filename)
    const tick = async (): Promise<void> => {
      try {
        const job = await api.getDeleteJob(jobId)
        deleteJobs[filename] = {
          ...deleteJobs[filename],
          jobId,
          status: job.status,
          message: job.message || "",
          steps: toSteps(job.steps, DELETE_STEP_KEYS),
        }
        if (job.status === "completed") {
          stopDeletePoll(filename)
          removeAfterDelay(filename)
        } else if (job.status === "failed") {
          stopDeletePoll(filename)
          deleteJobs[filename] = { ...deleteJobs[filename], error: job.error || "" }
        }
      } catch (err: unknown) {
        stopDeletePoll(filename)
        deleteJobs[filename] = { ...deleteJobs[filename], status: "failed", error: describeError(err) }
      }
    }
    void tick()
    deleteTimers[filename] = setInterval(() => void tick(), POLL_INTERVAL_MS)
  }

  function removeAfterDelay(filename: string): void {
    clearRemoveTimer(filename)
    removeTimers[filename] = setTimeout(() => {
      documents.value = documents.value.filter((d) => d.filename !== filename)
      delete deleteJobs[filename]
      clearRemoveTimer(filename)
      void refresh()
    }, REMOVE_AFTER_MS)
  }

  /** 确认对话框在组件层：这里只负责"已经决定要删"之后的事 */
  async function remove(filename: string): Promise<void> {
    if (deleteJobs[filename]?.status === "running") return
    clearRemoveTimer(filename)
    deleteJobs[filename] = { jobId: "", status: "running", message: "", error: "", collapsed: false, steps: blankSteps(DELETE_STEP_KEYS) }
    try {
      const job = await api.startDeleteJob(filename)
      deleteJobs[filename] = { ...deleteJobs[filename], jobId: job.job_id, message: job.message }
      startDeletePoll(filename, job.job_id)
    } catch (err: unknown) {
      deleteJobs[filename] = { ...deleteJobs[filename], status: "failed", error: describeError(err) }
    }
  }

  function reset(): void {
    stopUploadPoll()
    for (const filename of Object.keys(deleteTimers)) stopDeletePoll(filename)
    for (const filename of Object.keys(removeTimers)) clearRemoveTimer(filename)
    for (const filename of Object.keys(deleteJobs)) delete deleteJobs[filename]
    documents.value = []
    selectedFile.value = null
    isUploading.value = false
    uploadSteps.value = []
    uploadMessage.value = ""
    uploadError.value = ""
    uploadCollapsed.value = false
  }

  return {
    documents,
    isLoading,
    selectedFile,
    isUploading,
    uploadSteps,
    uploadMessage,
    uploadError,
    uploadCollapsed,
    deleteJobs,
    refresh,
    selectFile,
    upload,
    remove,
    reset,
  }
}
