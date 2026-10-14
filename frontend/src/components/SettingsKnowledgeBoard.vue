<template>
  <div class="docs-section">
    <div class="docs-head">
      <h3><Icon name="database" :size="16" />{{ $t("settings.docs_title") }}</h3>
      <p>{{ $t("settings.docs_desc") }}</p>
    </div>

    <section class="upload-section">
      <h3><Icon name="upload" :size="16" />{{ $t("settings.upload_title") }}</h3>
      <div class="upload-area">
        <input type="file" ref="fileInputRef" @change="onFileSelect" accept=".pdf,.doc,.docx,.xls,.xlsx" style="display:none" />
        <button @click="fileInputRef?.click()" class="upload-btn"><Icon name="upload" :size="15" />{{ $t("settings.select_file") }}</button>
        <div v-if="selectedFile" class="selected-file">
          <Icon name="file" :size="17" />
          <span>{{ selectedFile.name }}</span>
          <button @click="upload" class="btn-primary" :disabled="isUploading">
            <span v-if="isUploading" class="spinner"></span>
            <Icon v-else name="upload" :size="14" />
            {{ isUploading ? $t("settings.uploading") : $t("settings.start_upload") }}
          </button>
        </div>
        <div v-if="uploadSteps.length" class="upload-progress" :class="{ collapsed: uploadCollapsed }">
          <button type="button" class="upload-progress-header" @click="uploadCollapsed = !uploadCollapsed">
            <span class="upload-message">{{ uploadText }}</span>
            <span class="upload-toggle">{{ uploadCollapsed ? $t("settings.expand") : $t("settings.collapse") }}</span>
          </button>
          <div v-show="!uploadCollapsed" class="upload-step-list">
            <div v-for="step in uploadSteps" :key="step.key" class="upload-step" :class="`upload-step-${step.status}`">
              <div class="upload-step-header">
                <span class="upload-step-label">{{ stepLabel(step, "upload_steps") }}</span>
                <span class="upload-step-percent">{{ step.percent }}%</span>
              </div>
              <div class="upload-step-bar"><div class="upload-step-fill" :style="{ width: step.percent + '%' }"></div></div>
              <div v-if="step.message" class="upload-step-message">{{ step.message }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="documents-section">
      <h3><Icon name="database" :size="16" />{{ $t("settings.documents_title") }}</h3>
      <div v-if="isLoading" class="loading-indicator"><span class="spinner"></span></div>
      <div v-else-if="!documents.length" class="empty-documents">
        <Icon name="inbox" :size="30" />
        <p>{{ $t("settings.empty_documents") }}</p>
      </div>
      <div v-else class="documents-list">
        <div v-for="doc in documents" :key="doc.filename" class="document-item" :class="{ deleting: deleteJobs[doc.filename]?.status === 'running' }">
          <div class="document-main">
            <div class="document-row">
              <div class="document-info">
                <div class="document-icon" :class="`tone-${fileTone(doc.file_type)}`">{{ doc.file_type }}</div>
                <div class="document-details">
                  <div class="document-name">{{ doc.filename }}</div>
                  <div class="document-meta">
                    <span>{{ doc.file_type }}</span>
                    <span>{{ $t("settings.chunk_count", { count: doc.chunk_count }) }}</span>
                  </div>
                </div>
              </div>
              <button @click="confirmDelete(doc.filename)" class="btn-danger" :disabled="isDeleting(doc.filename)" :title="$t('settings.delete')">
                <Icon :name="deleteIcon(doc.filename)" :size="14" />
              </button>
            </div>
            <div v-if="deleteJobs[doc.filename]" class="upload-progress delete-progress" :class="{ collapsed: deleteJobs[doc.filename].collapsed }">
              <button type="button" class="upload-progress-header" @click="toggleDelete(doc.filename)">
                <span class="upload-message">{{ deleteText(doc.filename) }}</span>
                <span class="upload-toggle">{{ deleteJobs[doc.filename].collapsed ? $t('settings.expand') : $t('settings.collapse') }}</span>
              </button>
              <div v-show="!deleteJobs[doc.filename].collapsed" class="upload-step-list">
                <div v-for="step in deleteJobs[doc.filename].steps" :key="step.key" class="upload-step" :class="`upload-step-${step.status}`">
                  <div class="upload-step-header">
                    <span class="upload-step-label">{{ stepLabel(step, "delete_steps") }}</span>
                    <span class="upload-step-percent">{{ step.percent }}%</span>
                  </div>
                  <div class="upload-step-bar"><div class="upload-step-fill" :style="{ width: step.percent + '%' }"></div></div>
                  <div v-if="step.message" class="upload-step-message">{{ step.message }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// 知识库管理板块（仅管理员可见）。
//
// 整块按角色收起的理由要说死：`backend/api/documents.py` 的**每个**端点都是
// `Depends(require_admin)`，所以这不是"要不要给普通用户看"的产品选择，而是打了也是 403。
// 拆成独立组件另有一层用意：文档接口明天迁到 Go 时，需要改的只有这一个文件。
import { computed, ref } from "vue"
import Icon from "./Icon.vue"
import { useDocuments } from "../composables/useDocuments"
import type { StepView } from "../composables/useDocuments"
import { fileTone } from "../utils/fileIcon"
import { alertDialog, confirmDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"

const {
  documents,
  isLoading,
  selectedFile,
  isUploading,
  uploadSteps,
  uploadMessage,
  uploadError,
  uploadCollapsed,
  deleteJobs,
  refresh: refreshDocuments,
  selectFile,
  upload: startUpload,
  remove: removeDocument,
} = useDocuments()

const fileInputRef = ref<HTMLInputElement | null>(null)

const uploadText = computed(() => uploadError.value || uploadMessage.value || t("settings.upload_progress"))

/**
 * 视图的「刷新」按钮与挂载后的首次加载都走这里，所以本组件自己不 onMounted——
 * 两处各拉一次会白打一次请求，而且失败时会弹两条一样的红提示。
 */
async function refresh(): Promise<void> {
  try {
    await refreshDocuments()
  } catch (err: unknown) {
    alertDialog(`${t("settings.load_failed")}${describeError(err)}`)
  }
}

defineExpose({ refresh })

function deleteText(filename: string): string {
  const job = deleteJobs[filename]
  return job.error || job.message || t("settings.upload_progress")
}

/** 步骤名优先走 i18n（切语言时跟着变），i18n 里没有这个 key 才退回后端原样下发的 label */
function stepLabel(step: StepView, section: "upload_steps" | "delete_steps"): string {
  const key = `settings.${section}.${step.key}`
  const translated = t(key)
  return translated === key ? step.label : translated
}

function isDeleting(filename: string): boolean {
  const status = deleteJobs[filename]?.status
  return status === "running" || status === "completed"
}

function deleteIcon(filename: string): string {
  const status = deleteJobs[filename]?.status
  if (status === "running") return "refresh"
  if (status === "completed") return "check"
  return "trash"
}

function onFileSelect(e: Event): void {
  const input = e.target as HTMLInputElement
  selectFile(input.files?.[0] || null)
}

// startUpload / removeDocument 内部已经吃掉错误并落到状态里（模板只渲染），所以这里不 catch
function upload(): void {
  void startUpload()
}

async function confirmDelete(filename: string): Promise<void> {
  const confirmed = await confirmDialog(t("settings.delete_confirm_detail", { name: filename }))
  if (!confirmed) return
  void removeDocument(filename)
}

function toggleDelete(filename: string): void {
  const job = deleteJobs[filename]
  if (job) job.collapsed = !job.collapsed
}
</script>

<style scoped>
.docs-head { margin: 6px 0 14px; }
.docs-head h3 { display: flex; align-items: center; gap: 9px; font-size: 14.5px; color: var(--text-strong); }
.docs-head p { margin-top: 4px; font-size: 12.5px; color: var(--text-muted); }
</style>
