<template>
  <div class="page-inner">
    <PageHeader icon="sliders" title-key="views.settings.title" desc-key="settings.desc">
      <button class="btn-secondary" @click="reload"><Icon name="refresh" :size="14" />{{ $t("settings.refresh") }}</button>
    </PageHeader>

    <div class="grid grid-2 boards">
      <section class="card">
        <div class="card-head">
          <div>
            <h3>{{ $t("settings.account_title") }}</h3>
            <div class="sub">{{ $t("settings.account_desc") }}</div>
          </div>
          <Icon name="users" :size="16" />
        </div>
        <div class="card-body">
          <div class="account-row">
            <div class="account-avatar">{{ initial }}</div>
            <div class="account-id">
              <div class="account-name">{{ username }}</div>
              <span class="badge" :class="{ 'badge-accent': isAdmin }">{{ $t(`nav.roles.${role}`) }}</span>
            </div>
          </div>
          <p class="hint">{{ isAdmin ? $t("settings.account_admin_hint") : $t("settings.account_user_hint") }}</p>
          <div class="board-actions">
            <button class="btn-secondary" @click="logout">
              <Icon name="logout" :size="14" />{{ $t("settings.account_logout") }}
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div>
            <h3>{{ $t("settings.appearance_title") }}</h3>
            <div class="sub">{{ $t("settings.appearance_desc") }}</div>
          </div>
          <Icon name="eye" :size="16" />
        </div>
        <div class="card-body">
          <div class="theme-picker">
            <button
              v-for="opt in THEME_OPTIONS"
              :key="opt.value"
              type="button"
              :class="['theme-option', { active: draft.theme === opt.value }]"
              :disabled="isSaving"
              @click="pickTheme(opt.value)"
            >
              <Icon :name="opt.icon" :size="16" />
              <span class="theme-name">{{ $t(opt.labelKey) }}</span>
              <span class="theme-hint">{{ $t(opt.hintKey) }}</span>
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div>
            <h3>{{ $t("settings.prefs_title") }}</h3>
            <div class="sub">{{ $t("settings.prefs_desc") }}</div>
          </div>
          <Icon name="target" :size="16" />
        </div>
        <div class="card-body">
          <div class="field-block">
            <label class="field-label" for="prefs-start-view">{{ $t("settings.prefs_start_view") }}</label>
            <select id="prefs-start-view" v-model="draft.start_view" class="select">
              <option v-for="key in startViewOptions" :key="key" :value="key">{{ $t(`nav.items.${key}`) }}</option>
            </select>
          </div>
          <div class="board-actions">
            <button class="btn-primary" :disabled="isSaving" @click="savePreferences">
              <span v-if="isSaving" class="spinner"></span>
              <Icon v-else name="check" :size="14" />
              {{ isSaving ? $t("settings.saving") : $t("settings.save") }}
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div>
            <h3>{{ $t("settings.password_title") }}</h3>
            <div class="sub">{{ $t("settings.password_desc") }}</div>
          </div>
          <Icon name="shield" :size="16" />
        </div>
        <div class="card-body">
          <div class="field-block">
            <label class="field-label" for="pwd-old">{{ $t("settings.password_old") }}</label>
            <input id="pwd-old" v-model="password.old" type="password" class="input" autocomplete="current-password" />
          </div>
          <div class="field-block">
            <label class="field-label" for="pwd-new">{{ $t("settings.password_new") }}</label>
            <input id="pwd-new" v-model="password.next" type="password" class="input" autocomplete="new-password" />
          </div>
          <div class="field-block">
            <label class="field-label" for="pwd-confirm">{{ $t("settings.password_confirm") }}</label>
            <input id="pwd-confirm" v-model="password.confirm" type="password" class="input" autocomplete="new-password" />
          </div>
          <p class="hint">{{ $t("settings.password_rule_hint") }}</p>
          <div class="board-actions">
            <button class="btn-primary" :disabled="isChangingPassword" @click="submitPassword">
              <span v-if="isChangingPassword" class="spinner"></span>
              <Icon v-else name="shield" :size="14" />
              {{ isChangingPassword ? $t("settings.password_submitting") : $t("settings.password_submit") }}
            </button>
          </div>
        </div>
      </section>
    </div>

    <!-- 知识库管理：文档接口是 admin-only（backend/api/documents.py 全部 require_admin），所以整块按角色收起 -->
    <template v-if="isAdmin">
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import PageHeader from "../components/PageHeader.vue"
import Icon from "../components/Icon.vue"
import { useAuth } from "../composables/useAuth"
import { useAppSession } from "../composables/useAppSession"
import { useDocuments } from "../composables/useDocuments"
import type { StepView } from "../composables/useDocuments"
import { usePreferences, DEFAULT_PREFERENCES } from "../composables/usePreferences"
import { NAV_GROUPS } from "../composables/useNav"
import { fileTone } from "../utils/fileIcon"
import { alertDialog, confirmDialog, notifyDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"
import type { Theme, UserPreferences } from "../api/types"

const router = useRouter()
const { username, role, isAdmin, changePassword } = useAuth()
const { signOut } = useAppSession()
const { preferences, isSaving, load: loadPreferences, save: savePreferencesStore } = usePreferences()
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

const initial = computed(() => (username.value.slice(0, 1) || "?").toUpperCase())

// 主题三选一：value 必须与迁移 CHECK / Go 常量 / 契约 enum 一致（utils/theme.ts 顶部的注释）
const THEME_OPTIONS: { value: Theme; icon: string; labelKey: string; hintKey: string }[] = [
  { value: "light", icon: "sun", labelKey: "settings.theme_light", hintKey: "settings.theme_light_hint" },
  { value: "dark", icon: "moon", labelKey: "settings.theme_dark", hintKey: "settings.theme_dark_hint" },
  { value: "system", icon: "monitor", labelKey: "settings.theme_system", hintKey: "settings.theme_system_hint" },
]

// 落地页候选直接取自导航模型：后端只校验 slug 形状，认不认识由前端路由表说了算
const startViewOptions = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.key))

/** 编辑草稿：两个板块共用一个 PUT，所以本地持有一份完整对象，避免"改主题把落地页覆盖成默认" */
const draft = reactive<UserPreferences>({ ...DEFAULT_PREFERENCES })
watch(
  preferences,
  (next) => {
    draft.theme = next.theme
    draft.start_view = next.start_view
  },
  { immediate: true, deep: true },
)

const password = reactive({ old: "", next: "", confirm: "" })
const isChangingPassword = ref(false)

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
  if (status === "running") return "refresh"
  if (status === "completed") return "check"
  return "trash"
}

onMounted(() => { void reload() })

async function reload(): Promise<void> {
  try {
    await loadPreferences()
  } catch (err: unknown) {
    alertDialog(`${t("settings.prefs_load_failed")}${describeError(err)}`)
  }
  if (!isAdmin.value) return
  try {
    await refreshDocuments()
  } catch (err: unknown) {
    alertDialog(`${t("settings.load_failed")}${describeError(err)}`)
  }
}

function logout(): void {
  signOut()
  void router.replace({ name: "login" })
}

/** 主题是即时生效的开关：先本地应用（用户马上看到效果），再把整份偏好写回后端 */
async function pickTheme(theme: Theme): Promise<void> {
  const previous = draft.theme
  draft.theme = theme
  try {
    await savePreferencesStore({ ...draft })
  } catch (err: unknown) {
    draft.theme = previous
    alertDialog(`${t("settings.save_failed")}${describeError(err)}`)
  }
}

async function savePreferences(): Promise<void> {
  try {
    await savePreferencesStore({ ...draft })
    notifyDialog(t("settings.saved"))
  } catch (err: unknown) {
    alertDialog(`${t("settings.save_failed")}${describeError(err)}`)
  }
}

async function submitPassword(): Promise<void> {
  if (!password.old || !password.next) {
    alertDialog(t("settings.password_required"))
    return
  }
  if (password.next !== password.confirm) {
    alertDialog(t("settings.password_mismatch"))
    return
  }
  isChangingPassword.value = true
  try {
    // 强度规则由后端判定（与注册同一条），前端不复刻，避免两处规则漂移
    await changePassword({ old_password: password.old, new_password: password.next })
    password.old = ""
    password.next = ""
    password.confirm = ""
    notifyDialog(t("settings.password_changed"))
  } catch (err: unknown) {
    alertDialog(`${t("settings.password_failed")}${describeError(err)}`)
  } finally {
    isChangingPassword.value = false
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
.boards { margin-bottom: 16px; align-items: start; }
.account-row { display: flex; align-items: center; gap: 12px; }
.account-avatar {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 17px;
  font-weight: 650;
  text-transform: uppercase;
}
.account-id { display: flex; flex-direction: column; gap: 5px; align-items: flex-start; min-width: 0; }
.account-name { font-size: 15px; font-weight: 600; color: var(--text-strong); overflow-wrap: anywhere; }
.hint { font-size: 12.5px; color: var(--text-faint); line-height: 1.55; margin-top: 12px; }
.board-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

.field-block { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.field-block:last-of-type { margin-bottom: 0; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text-muted); }

.theme-picker { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
@media (max-width: 560px) { .theme-picker { grid-template-columns: minmax(0, 1fr); } }
.theme-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  font-family: inherit;
  text-align: center;
  color: var(--text-muted);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  cursor: pointer;
  transition: var(--transition);
}
.theme-option:hover:not(:disabled) { background: var(--bg-hover); }
.theme-option:disabled { opacity: .6; cursor: not-allowed; }
.theme-option.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.theme-name { font-size: 13px; font-weight: 600; color: var(--text-strong); }
.theme-option.active .theme-name { color: var(--accent); }
.theme-hint { font-size: 11px; color: var(--text-faint); line-height: 1.4; }
.theme-option.active .theme-hint { color: var(--text-muted); }

.docs-head { margin: 6px 0 14px; }
.docs-head h3 { display: flex; align-items: center; gap: 9px; font-size: 14.5px; color: var(--text-strong); }
.docs-head p { margin-top: 4px; font-size: 12.5px; color: var(--text-muted); }
</style>
