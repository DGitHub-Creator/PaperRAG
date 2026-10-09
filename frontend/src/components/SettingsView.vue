<template>
  <div class="settings-panel">
    <div class="settings-header">
      <h2><i class="fas fa-cog"></i> {{ $t("settings.title") }}</h2>
      <p>{{ $t("settings.desc") }}</p>
    </div>

    <div class="upload-section">
      <h3><i class="fas fa-upload"></i> {{ $t("settings.upload_title") }}</h3>
      <div class="upload-area">
        <input type="file" ref="fileInputRef" @change="onFileSelect" accept=".pdf,.doc,.docx,.xls,.xlsx" style="display:none" />
        <button @click="fileInputRef?.click()" class="upload-btn"><i class="fas fa-cloud-upload-alt"></i> {{ $t("settings.select_file") }}</button>
        <div v-if="selectedFile" class="selected-file">
          <i class="fas fa-file"></i> {{ selectedFile.name }}
          <button @click="upload" class="btn-primary" :disabled="isUploading"><i class="fas fa-upload"></i> {{ isUploading ? $t('settings.uploading') : $t('settings.start_upload') }}</button>
        </div>
        <div v-if="uploadSteps.length" class="upload-progress" :class="{ collapsed: uploadCollapsed }">
          <button type="button" class="upload-progress-header" @click="uploadCollapsed = !uploadCollapsed">
            <span class="upload-message">{{ uploadText }}</span>
            <span class="upload-toggle">{{ uploadCollapsed ? $t('settings.expand') : $t('settings.collapse') }}</span>
          </button>
          <div v-show="!uploadCollapsed" class="upload-step-list">
            <div v-for="step in uploadSteps" :key="step.key" class="upload-step" :class="`upload-step-${step.status}`">
              <div class="upload-step-header">
                <span class="upload-step-label">{{ stepLabel(step, 'upload_steps') }}</span>
                <span class="upload-step-percent">{{ step.percent }}%</span>
              </div>
              <div class="upload-step-bar"><div class="upload-step-fill" :style="{ width: step.percent + '%' }"></div></div>
              <div v-if="step.message" class="upload-step-message">{{ step.message }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="documents-section">
      <h3><i class="fas fa-list"></i> {{ $t("settings.documents_title") }}</h3>
      <button @click="reload" class="btn-secondary"><i class="fas fa-sync"></i> {{ $t("settings.refresh") }}</button>
      <div v-if="isLoading" class="loading-indicator">{{ $t("app.loading") }}</div>
      <div v-else-if="!documents.length" class="empty-documents"><i class="fas fa-inbox"></i><p>{{ $t("settings.empty_documents") }}</p></div>
      <div v-else class="documents-list">
        <div v-for="doc in documents" :key="doc.filename" class="document-item" :class="{ deleting: deleteJobs[doc.filename]?.status === 'running' }">
          <div class="document-main">
            <div class="document-row">
              <div class="document-info">
                <div class="document-icon"><i :class="fileIcon(doc.file_type)"></i></div>
                <div class="document-details">
                  <div class="document-name">{{ doc.filename }}</div>
                  <div class="document-meta">
                    <span>{{ doc.file_type }}</span>
                    <span>{{ $t("settings.chunk_count", { count: doc.chunk_count }) }}</span>
                  </div>
                </div>
              </div>
              <button @click="confirmDelete(doc.filename)" class="btn-danger" :disabled="isDeleting(doc.filename)" :title="$t('settings.delete')">
                <i :class="deleteIcon(doc.filename)"></i>
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
                    <span class="upload-step-label">{{ stepLabel(step, 'delete_steps') }}</span>
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useDocuments } from "../composables/useDocuments"
import type { StepView } from "../composables/useDocuments"
import { fileIcon } from "../utils/fileIcon"
import { alertDialog, confirmDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"

const fileInputRef = ref<HTMLInputElement | null>(null)
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
  refresh,
  selectFile,
  upload: startUpload,
  remove: removeDocument,
} = useDocuments()

const uploadText = computed(() => uploadError.value || uploadMessage.value || t("settings.upload_progress"))

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
  if (status === "running") return "fas fa-spinner fa-spin"
  if (status === "completed") return "fas fa-check"
  return "fas fa-trash"
}

onMounted(() => { void reload() })

async function reload(): Promise<void> {
  try {
    await refresh()
  } catch (err: unknown) {
    alertDialog(`${t("settings.load_failed")}${describeError(err)}`)
  }
}

function onFileSelect(e: Event): void {
  const input = e.target as HTMLInputElement
  selectFile(input.files?.[0] || null)
}

// upload / remove 内部已经吃掉错误并落到状态里（组件只渲染），所以这里不 catch
function upload(): void {
  void startUpload()
}

function confirmDelete(filename: string): void {
  if (!confirmDialog(t("settings.delete_confirm_detail", { name: filename }))) return
  void removeDocument(filename)
}

function toggleDelete(filename: string): void {
  const job = deleteJobs[filename]
  if (job) job.collapsed = !job.collapsed
}
</script>
