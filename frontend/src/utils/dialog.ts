// 对话框的唯一出口（`docs/rules/10-frontend-structure.md` R3）：状态层不调 alert/confirm，
// 只有组件能通过这里提问。2026-10-14 起底座从 window.alert/confirm 换成站内 toast 与自定义确认框
// （原生弹窗在科研工作台里太打断，且 confirm 的同步返回值没法做"待处理"态）——
// 调用方的差别只有一个 await，将来换实现仍只改这一个文件。
import { useConfirm } from "../composables/useConfirm"
import type { ConfirmOptions } from "../composables/useConfirm"
import { useToast } from "../composables/useToast"

/** 提示（原 window.alert）：不阻塞，右下沉一条，错误默认常驻等用户关掉 */
export function alertDialog(message: string): void {
  useToast().error(message)
}

/** 成功/中性提示：自动消失，用于"已保存""密码已修改"这类不需要用户处置的回执 */
export function notifyDialog(message: string, tone: "ok" | "info" = "ok"): void {
  const toast = useToast()
  if (tone === "ok") toast.ok(message)
  else toast.info(message)
}

/** 确认（原 window.confirm）：返回值从 boolean 变成 Promise<boolean>，所以调用方必须 await */
export function confirmDialog(message: string, options?: Omit<ConfirmOptions, "message">): Promise<boolean> {
  return useConfirm().ask({ message, ...options })
}
