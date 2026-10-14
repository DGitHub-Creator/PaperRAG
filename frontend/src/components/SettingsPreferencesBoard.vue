<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>{{ $t("settings.prefs_title") }}</h3>
        <div class="sub">{{ $t("settings.prefs_desc") }}</div>
      </div>
      <Icon name="target" :size="16" />
    </div>
    <div class="card-body">
      <div class="sb-field">
        <label class="sb-field-label" for="prefs-start-view">{{ $t("settings.prefs_start_view") }}</label>
        <select id="prefs-start-view" v-model="draft.start_view" class="select">
          <option v-for="key in startViewOptions" :key="key" :value="key">{{ $t(`nav.items.${key}`) }}</option>
        </select>
      </div>
      <div class="sb-actions">
        <button class="btn-primary" :disabled="isSaving" @click="save">
          <span v-if="isSaving" class="spinner"></span>
          <Icon v-else name="check" :size="14" />
          {{ isSaving ? $t("settings.saving") : $t("settings.save") }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 偏好板块：目前只有一项「登录后落在哪一页」。
// 选项直接取自导航模型，不新起一份路由清单——清单有两份就一定会漂（同 10 §7.1 对 NavKey 的要求）。
import Icon from "./Icon.vue"
import { usePreferences } from "../composables/usePreferences"
import { NAV_GROUPS } from "../composables/useNav"
import { alertDialog, notifyDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"

const { draft, isSaving, saveDraft } = usePreferences()

const startViewOptions = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.key))

async function save(): Promise<void> {
  try {
    await saveDraft()
    notifyDialog(t("settings.saved"))
  } catch (err: unknown) {
    alertDialog(`${t("settings.save_failed")}${describeError(err)}`)
  }
}
</script>
