// 确认框的状态（R3 状态层不碰 DOM）：ask() 返回 Promise，渲染由 components/ConfirmHost.vue 负责。
// 与 window.confirm 的差别就是"同步返回值变成了 Promise"——调用方加一个 await，其余不变。
import { ref } from "vue"

export interface ConfirmOptions {
  message: string
  titleKey?: string
  confirmKey?: string
  cancelKey?: string
  /** 破坏性操作用红色确认键（删除、清空） */
  danger?: boolean
}

export interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void
}

const pending = ref<PendingConfirm | null>(null)

export function useConfirm() {
  function ask(options: ConfirmOptions): Promise<boolean> {
    // 同一时刻只留一个确认框：并发 ask 时把先前那个按"取消"结算，避免前一个 Promise 永远挂着
    if (pending.value) pending.value.resolve(false)
    return new Promise<boolean>((resolve) => {
      pending.value = { ...options, resolve }
    })
  }

  function settle(ok: boolean): void {
    const current = pending.value
    pending.value = null
    if (current) current.resolve(ok)
  }

  return { pending, ask, settle }
}
