<template>
  <div class="settings-panel">
    <div class="settings-header">
      <h2><i class="fas fa-cog"></i> 文档管理</h2>
      <p>上传文档进行向量化处理，支持 PDF / Word / Excel 格式</p>
    </div>

    <div class="upload-section">
      <h3><i class="fas fa-upload"></i> 上传文档</h3>
      <div class="upload-area">
        <input type="file" ref="fileInputRef" @change="onFileSelect" accept=".pdf,.doc,.docx,.xls,.xlsx" style="display:none" />
        <button @click="fileInputRef?.click()" class="upload-btn"><i class="fas fa-cloud-upload-alt"></i> 选择文件</button>
        <div v-if="selectedFile" class="selected-file">
          <i class="fas fa-file"></i> {{ selectedFile.name }}
          <button @click="upload" class="btn-primary" :disabled="isUploading"><i class="fas fa-upload"></i> {{ isUploading ? '上传中...' : '开始上传' }}</button>
        </div>
        <div v-if="uploadSteps.length" class="upload-progress" :class="{ collapsed: uploadCollapsed }">
          <button type="button" class="upload-progress-header" @click="uploadCollapsed = !uploadCollapsed">
            <span class="upload-message">{{ uploadProgress || '上传进度' }}</span>
            <span class="upload-toggle">{{ uploadCollapsed ? '展开' : '收起' }}</span>
          </button>
          <div v-show="!uploadCollapsed" class="upload-step-list">
            <div v-for="step in uploadSteps" :key="step.key" class="upload-step" :class="`upload-step-${step.status}`">
              <div class="upload-step-header">
                <span class="upload-step-label">{{ step.label }}</span>
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
      <h3><i class="fas fa-list"></i> 已上传文档</h3>
      <button @click="load" class="btn-secondary"><i class="fas fa-sync"></i> 刷新列表</button>
      <div v-if="documentsLoading" class="loading-indicator">加载中...</div>
      <div v-else-if="!documents.length" class="empty-documents"><i class="fas fa-inbox"></i><p>暂无文档</p></div>
      <div v-else class="documents-list">
        <div v-for="doc in documents" :key="doc.filename" class="document-item" :class="{ deleting: deleteJobs[doc.filename]?.status === 'running' }">
          <div class="document-main">
            <div class="document-row">
              <div class="document-info">
                <div class="document-icon"><i :class="getFileIcon(doc.file_type)"></i></div>
                <div class="document-details">
                  <div class="document-name">{{ doc.filename }}</div>
                  <div class="document-meta"><span>{{ doc.file_type }}</span><span>{{ doc.chunk_count }} 个文本片段</span></div>
                </div>
              </div>
              <button @click="deleteDoc(doc.filename)" class="btn-danger" :disabled="deleteJobs[doc.filename]?.status === 'running' || deleteJobs[doc.filename]?.status === 'completed'" title="删除">
                <i :class="deleteJobs[doc.filename]?.status === 'running' ? 'fas fa-spinner fa-spin' : deleteJobs[doc.filename]?.status === 'completed' ? 'fas fa-check' : 'fas fa-trash'"></i>
              </button>
            </div>
            <div v-if="deleteJobs[doc.filename]" class="upload-progress delete-progress" :class="{ collapsed: deleteJobs[doc.filename].collapsed }">
              <button type="button" class="upload-progress-header" @click="deleteJobs[doc.filename].collapsed = !deleteJobs[doc.filename].collapsed">
                <span class="upload-message">{{ deleteJobs[doc.filename].message || '删除进度' }}</span>
                <span class="upload-toggle">{{ deleteJobs[doc.filename].collapsed ? '展开' : '收起' }}</span>
              </button>
              <div v-show="!deleteJobs[doc.filename].collapsed" class="upload-step-list">
                <div v-for="step in deleteJobs[doc.filename].steps" :key="step.key" class="upload-step" :class="`upload-step-${step.status}`">
                  <div class="upload-step-header"><span class="upload-step-label">{{ step.label }}</span><span class="upload-step-percent">{{ step.percent }}%</span></div>
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
import { ref, onMounted, onBeforeUnmount } from "vue"
import { useDocuments } from "../composables/useDocuments"

import { getFileIcon } from "../services/api"
const fileInputRef = ref<HTMLInputElement | null>(null)
const { documents, documentsLoading, selectedFile, isUploading, uploadProgress, uploadSteps, uploadCollapsed, deleteJobs, load, upload, deleteDoc, stopUploadPoll } = useDocuments()

onMounted(() => load())
onBeforeUnmount(() => { stopUploadPoll() })

function onFileSelect(e: Event): void {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    selectedFile.value = input.files[0]
    uploadProgress.value = ""
    uploadSteps.value = []
    uploadCollapsed.value = false
  }
}
</script>
