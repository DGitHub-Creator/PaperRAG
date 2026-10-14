<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>{{ $t("settings.password_title") }}</h3>
        <div class="sub">{{ $t("settings.password_desc") }}</div>
      </div>
      <Icon name="shield" :size="16" />
    </div>
    <div class="card-body">
      <div class="sb-field">
        <label class="sb-field-label" for="pwd-old">{{ $t("settings.password_old") }}</label>
        <input id="pwd-old" v-model="form.old" type="password" class="input" autocomplete="current-password" />
      </div>
      <div class="sb-field">
        <label class="sb-field-label" for="pwd-new">{{ $t("settings.password_new") }}</label>
        <input id="pwd-new" v-model="form.next" type="password" class="input" autocomplete="new-password" />
      </div>
      <div class="sb-field">
        <label class="sb-field-label" for="pwd-confirm">{{ $t("settings.password_confirm") }}</label>
        <input id="pwd-confirm" v-model="form.confirm" type="password" class="input" autocomplete="new-password" />
      </div>
      <p class="sb-hint">{{ $t("settings.password_rule_hint") }}</p>
      <div class="sb-actions">
        <button class="btn-primary" :disabled="busy" @click="submit">
          <span v-if="busy" class="spinner"></span>
          <Icon v-else name="shield" :size="14" />
          {{ busy ? $t("settings.password_submitting") : $t("settings.password_submit") }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 改密码板块。前端只做「非空 + 两次一致」两条本地检查，**强度规则不复刻**——
// 那条规则归后端（与注册同一条：码点长度 + 至少两类字符），两处各写一份必然漂移。
import { reactive, ref } from "vue"
import Icon from "./Icon.vue"
import { useAuth } from "../composables/useAuth"
import { alertDialog, notifyDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"

const { changePassword } = useAuth()

const form = reactive({ old: "", next: "", confirm: "" })
const busy = ref(false)

async function submit(): Promise<void> {
  if (!form.old || !form.next) {
    alertDialog(t("settings.password_required"))
    return
  }
  if (form.next !== form.confirm) {
    alertDialog(t("settings.password_mismatch"))
    return
  }
  busy.value = true
  try {
    await changePassword({ old_password: form.old, new_password: form.next })
    form.old = ""
    form.next = ""
    form.confirm = ""
    notifyDialog(t("settings.password_changed"))
  } catch (err: unknown) {
    alertDialog(`${t("settings.password_failed")}${describeError(err)}`)
  } finally {
    busy.value = false
  }
}
</script>
