<template>
  <header class="topbar">
    <div class="topbar-title">
      <h1>{{ $t(current.titleKey) }}</h1>
      <span v-if="current.groupKey" class="crumb">{{ $t(current.groupKey) }}</span>
      <span v-if="current.badgeKey" class="badge badge-demo">{{ $t(current.badgeKey) }}</span>
    </div>
    <div class="topbar-actions">
      <div class="lang-switch">
        <button :class="{ active: locale === 'zh-CN' }" @click="pick('zh-CN')">{{ $t("app.lang_zh") }}</button>
        <button :class="{ active: locale === 'en' }" @click="pick('en')">{{ $t("app.lang_en") }}</button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { NAV_GROUPS } from "../composables/useNav"
import { setLocale } from "../i18n"

const route = useRoute()
const { locale } = useI18n()

// 标题与「示例数据」徽标都以路由为唯一来源：titleKey 来自 meta，徽标来自 NavKey → NAV_GROUPS 的映射，
// 这样"哪页是 mock"只在一处维护（composables/useNav.ts），不会文档一份、页面一份。
const flat = NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ item, group })))

const current = computed(() => {
  const name = String(route.name ?? "")
  const hit = flat.find((entry) => entry.item.key === name)
  return {
    titleKey: String(route.meta.titleKey ?? "app.short_title"),
    groupKey: hit ? hit.group.labelKey : "",
    badgeKey: hit?.item.badgeKey ?? "",
  }
})

function pick(code: string): void {
  setLocale(code)
}
</script>
