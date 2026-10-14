// 站内提示的唯一出口：状态层只往这里 push 一条消息，渲染交给 components/ToastHost.vue（R3 状态层不碰 DOM）。
// 与 utils/dialog.ts 的关系：alertDialog 是它的薄封装，调用方不必知道提示长什么样。
import { ref } from "vue"

export type ToastTone = "info" | "ok" | "error"

export interface Toast {
  id: number
  tone: ToastTone
  message: string
}

/** 自动消失时长；设 0 表示常驻（错误提示留给用户自己关，避免"一闪而过没看清"） */
const DEFAULT_MS = 4000

const toasts = ref<Toast[]>([])
let seq = 0

function push(tone: ToastTone, message: string, ms: number): number {
  const id = ++seq
  toasts.value = [...toasts.value, { id, tone, message }]
  if (ms > 0) setTimeout(() => dismiss(id), ms)
  return id
}

function dismiss(id: number): void {
  toasts.value = toasts.value.filter((item) => item.id !== id)
}

export function useToast() {
  function info(message: string, ms = DEFAULT_MS): number {
    return push("info", message, ms)
  }

  function ok(message: string, ms = DEFAULT_MS): number {
    return push("ok", message, ms)
  }

  /** 错误默认常驻：报错信息往往要读第二遍，自动消失等于没提示 */
  function error(message: string, ms = 0): number {
    return push("error", message, ms)
  }

  return { toasts, dismiss, info, ok, error }
}
