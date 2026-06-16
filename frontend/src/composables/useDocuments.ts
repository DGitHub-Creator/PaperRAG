import { ref, reactive } from "vue"
import { authFetch } from "../services/api"
import { t } from "../i18n"

interface StepState {
  key: string
  label: string
  percent: number
  status: string
  message: string
}

interface DeleteJobState {
  status: string
  message: string
  collapsed?: boolean
  jobId?: string
  steps: StepState[]
}

interface UploadJobResponse {
  job_id: string
  status: string
  message?: string
  steps?: StepState[]
}

interface DeleteJobResponse {
  job_id: string
  status: string
  message?: string
  steps?: StepState[]
}

interface DocumentRecord {
  filename: string
  file_type: string
  chunk_count?: number
}

const DEFAULT_UPLOAD_STEPS: StepState[] = [
  { key: "upload", label: "文档上传", percent: 0, status: "pending", message: "" },
  { key: "cleanup", label: "清理旧版本", percent: 0, status: "pending", message: "" },
  { key: "parse", label: "解析与分块", percent: 0, status: "pending", message: "" },
  { key: "parent_store", label: "父级分块入库", percent: 0, status: "pending", message: "" },
  { key: "vector_store", label: "向量化入库", percent: 0, status: "pending", message: "" },
]

const DEFAULT_DELETE_STEPS: StepState[] = [
  { key: "prepare", label: "准备删除", percent: 0, status: "pending", message: "" },
  { key: "bm25", label: "同步 BM25 统计", percent: 0, status: "pending", message: "" },
  { key: "milvus", label: "删除向量数据", percent: 0, status: "pending", message: "" },
  { key: "parent_store", label: "删除父级分块", percent: 0, status: "pending", message: "" },
]

export function useDocuments() {
  const documents = ref<DocumentRecord[]>([])
  const documentsLoading = ref(false)
  const selectedFile = ref<File | null>(null)
  const isUploading = ref(false)
  const uploadProgress = ref("")
  const uploadSteps = ref<StepState[]>([])
  const uploadCollapsed = ref(false)
  const activeUploadJobId = ref("")
  const deleteJobs: Record<string, DeleteJobState> = reactive({})
  let uploadTimer: ReturnType<typeof setInterval> | null = null
  const deleteTimers: Record<string, ReturnType<typeof setInterval>> = {}
  const removeTimers: Record<string, ReturnType<typeof setTimeout>> = {}

  function mergeDocs(next: DocumentRecord[] | undefined): DocumentRecord[] {
    const merged = [...(Array.isArray(next) ? next : [])]
    Object.keys(deleteJobs).forEach((fn) => {
      if (!merged.some((d) => d.filename === fn)) {
        const cur = documents.value.find((d) => d.filename === fn)
        if (cur) merged.push(cur)
      }
    })
    return merged
  }

  async function load(): Promise<void> {
    documentsLoading.value = true
    try {
      const res = await authFetch("/documents")
      if (!res.ok) throw new Error("加载失败")
      const data = await res.json()
      documents.value = mergeDocs(data.documents)
    } catch (e: unknown) { alert(t("settings.load_failed") + (e instanceof Error ? e.message : String(e))) }
    finally { documentsLoading.value = false }
  }

  function updateUploadStep(key: string, percent: number, status = "running", message = ""): void {
    if (!uploadSteps.value.length) uploadSteps.value = DEFAULT_UPLOAD_STEPS.map((s) => ({ ...s }))
    const idx = uploadSteps.value.findIndex((s) => s.key === key)
    if (idx === -1) return
    uploadSteps.value[idx] = { ...uploadSteps.value[idx], percent: Math.max(0, Math.min(100, percent)), status, message }
  }

  function syncUploadJob(job: UploadJobResponse): void {
    activeUploadJobId.value = job.job_id
    uploadProgress.value = job.message || ""
    if (Array.isArray(job.steps)) {
      uploadSteps.value = job.steps.map((s) => ({ key: s.key, label: s.label, percent: s.percent, status: s.status, message: s.message || "" }))
    }
    if (job.status === "completed") uploadCollapsed.value = true
  }

  function stopUploadPoll(): void {
    if (uploadTimer) { clearInterval(uploadTimer); uploadTimer = null }
  }

  function startUploadPoll(jobId: string): void {
    stopUploadPoll()
    const poll = async () => {
      try {
        const res = await authFetch(`/documents/upload/jobs/${encodeURIComponent(jobId)}`)
        if (!res.ok) throw new Error("查询失败")
        const job: UploadJobResponse = await res.json()
        syncUploadJob(job)
        if (job.status === "completed" || job.status === "failed") {
          stopUploadPoll()
          isUploading.value = false
          if (job.status === "completed") {
            selectedFile.value = null
            await load()
          }
        }
      } catch (e: unknown) {
        uploadProgress.value = t("settings.query_failed") + (e instanceof Error ? e.message : String(e))
        stopUploadPoll()
        isUploading.value = false
      }
    }
    poll()
    uploadTimer = setInterval(poll, 1000)
  }

  function uploadFile(file: File): Promise<UploadJobResponse> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const fd = new FormData()
      fd.append("file", file)
      xhr.open("POST", "/documents/upload/async")
      const token = localStorage.getItem("accessToken")
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`)
      xhr.upload.onprogress = (e: ProgressEvent) => {
        if (!e.lengthComputable) return
        updateUploadStep("upload", Math.round((e.loaded / e.total) * 100), "running", `已上传 ${Math.round(e.loaded / e.total * 100)}%`)
      }
      xhr.onload = () => {
        if (xhr.status === 401) { reject(new Error("登录已过期")); return }
        try {
          const data: UploadJobResponse = JSON.parse(xhr.responseText || "{}")
          if (xhr.status >= 200 && xhr.status < 300) { updateUploadStep("upload", 100, "completed"); resolve(data) }
          else reject(new Error(data.message || `HTTP ${xhr.status}`))
        } catch (_) { reject(new Error("解析失败")) }
      }
      xhr.onerror = () => reject(new Error("上传请求失败"))
      xhr.send(fd)
    })
  }

  async function upload(): Promise<void> {
    if (!selectedFile.value) { alert(t("settings.select_file")); return }
    isUploading.value = true
    uploadProgress.value = "正在上传..."
    uploadSteps.value = DEFAULT_UPLOAD_STEPS.map((s) => ({ ...s }))
    uploadCollapsed.value = false
    try {
      const data = await uploadFile(selectedFile.value)
      uploadProgress.value = data.message || ""
      startUploadPoll(data.job_id)
    } catch (e: unknown) {
      updateUploadStep("upload", 100, "failed", e instanceof Error ? e.message : String(e))
      uploadProgress.value = t("settings.upload_failed_prefix") + (e instanceof Error ? e.message : String(e))
      isUploading.value = false
    }
  }

  function stopDeletePoll(filename: string): void {
    if (deleteTimers[filename]) { clearInterval(deleteTimers[filename]); delete deleteTimers[filename] }
  }

  function clearRemoveTimer(filename: string): void {
    if (removeTimers[filename]) { clearTimeout(removeTimers[filename]); delete removeTimers[filename] }
  }

  function startDeletePoll(filename: string, jobId: string): void {
    stopDeletePoll(filename)
    const poll = async () => {
      try {
        const res = await authFetch(`/documents/delete/jobs/${encodeURIComponent(jobId)}`)
        if (!res.ok) throw new Error("查询失败")
        const job: DeleteJobResponse = await res.json()
        deleteJobs[filename] = {
          ...(deleteJobs[filename] || {}),
          status: job.status, message: job.message || "",
          steps: Array.isArray(job.steps) ? job.steps.map((s) => ({ ...s, message: s.message || "" })) : DEFAULT_DELETE_STEPS.map((s) => ({ ...s })),
        }
        if (job.status === "completed") { stopDeletePoll(filename); removeAfterDelay(filename) }
        else if (job.status === "failed") stopDeletePoll(filename)
      } catch (e: unknown) {
        stopDeletePoll(filename)
      }
    }
    poll()
    deleteTimers[filename] = setInterval(poll, 1000)
  }

  function removeAfterDelay(filename: string): void {
    clearRemoveTimer(filename)
    removeTimers[filename] = setTimeout(async () => {
      documents.value = documents.value.filter((d) => d.filename !== filename)
      delete deleteJobs[filename]
      clearRemoveTimer(filename)
      await load()
    }, 3000)
  }

  async function deleteDoc(filename: string): Promise<void> {
    if (deleteJobs[filename]?.status === "running") return
    if (!confirm(t("settings.delete_confirm_prefix") + filename + t("settings.delete_confirm_suffix"))) return
    clearRemoveTimer(filename)
    deleteJobs[filename] = { status: "running", message: "提交中...", collapsed: false, steps: DEFAULT_DELETE_STEPS.map((s, i) => i === 0 ? { ...s, percent: 1, status: "running", message: "提交中" } : { ...s }) }
    try {
      const res = await authFetch(`/documents/delete/async/${encodeURIComponent(filename)}`, { method: "DELETE" })
      if (!res.ok) throw new Error("删除失败")
      const data: DeleteJobResponse = await res.json()
      deleteJobs[filename] = { ...deleteJobs[filename], jobId: data.job_id, message: data.message || "删除中..." }
      startDeletePoll(filename, data.job_id)
    } catch (e: unknown) {
      deleteJobs[filename] = { ...deleteJobs[filename], status: "failed", message: "删除失败：" + (e instanceof Error ? e.message : String(e)) }
    }
  }

  return { documents, documentsLoading, selectedFile, isUploading, uploadProgress, uploadSteps, uploadCollapsed, activeUploadJobId, deleteJobs, load, upload, deleteDoc, updateUploadStep, syncUploadJob, stopUploadPoll, uploadFile }
}
