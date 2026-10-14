<template>
  <div class="page-inner">
    <PageHeader icon="sliders" title-key="views.settings.title" desc-key="settings.desc">
      <button class="btn-secondary" @click="reload"><Icon name="refresh" :size="14" />{{ $t("settings.refresh") }}</button>
    </PageHeader>

    <div class="grid grid-2 sb-boards">
      <SettingsAccountBoard />
      <SettingsThemeBoard />
      <SettingsPreferencesBoard />
      <SettingsPasswordBoard />
    </div>

    <!-- 知识库管理：文档接口是 admin-only（backend/api/documents.py 全部 require_admin），所以整块按角色收起 -->
    <SettingsKnowledgeBoard v-if="isAdmin" ref="knowledgeRef" />
  </div>
</template>

<script setup lang="ts">
// 设置页只做编排：四个板块 + 管理员多一块知识库。
// 状态与动作都在各板块自己的 composable 调用里（useAuth / usePreferences / useDocuments 都是模块级单例），
// 所以这里没有业务状态可放——视图的职责就只剩"决定谁出现"和"刷新时通知谁"。
import { onMounted, ref } from "vue"
import PageHeader from "../components/PageHeader.vue"
import Icon from "../components/Icon.vue"
import SettingsAccountBoard from "../components/SettingsAccountBoard.vue"
import SettingsThemeBoard from "../components/SettingsThemeBoard.vue"
import SettingsPreferencesBoard from "../components/SettingsPreferencesBoard.vue"
import SettingsPasswordBoard from "../components/SettingsPasswordBoard.vue"
import SettingsKnowledgeBoard from "../components/SettingsKnowledgeBoard.vue"
import { useAuth } from "../composables/useAuth"
import { usePreferences } from "../composables/usePreferences"
import { alertDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"

const { isAdmin } = useAuth()
const { load: loadPreferences } = usePreferences()

const knowledgeRef = ref<InstanceType<typeof SettingsKnowledgeBoard> | null>(null)

async function reload(): Promise<void> {
  try {
    await loadPreferences()
  } catch (err: unknown) {
    alertDialog(`${t("settings.prefs_load_failed")}${describeError(err)}`)
  }
  if (isAdmin.value) await knowledgeRef.value?.refresh()
}

// 用 onMounted 而不是在 setup 里直接调：那一条 await 之后才去碰 knowledgeRef，
// 而 ref 要到模板渲染完才填得上——挂在 onMounted 上这个顺序就是明摆着的。
onMounted(() => { void reload() })
</script>
