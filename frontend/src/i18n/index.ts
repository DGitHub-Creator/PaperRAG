import { createI18n } from "vue-i18n"
import zhCN from "./locales/zh-CN.json"
import en from "./locales/en.json"

export type LocaleKey = keyof typeof zhCN

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem("locale") || "zh-CN",
  fallbackLocale: "zh-CN",
  messages: { "zh-CN": zhCN, en },
})

export function setLocale(locale: string): void {
  i18n.global.locale.value = locale as any
  localStorage.setItem("locale", locale)
}

export function t(key: string, params?: Record<string, unknown>): string {
  return i18n.global.t(key, params || {})
}

export default i18n
