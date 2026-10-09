// 应用内事件总线（`docs/refactor/10` R7）。
// 之前 401 用裸 `window.dispatchEvent(new CustomEvent("auth-expired"))` 广播，
// 订阅方拿不到退订函数，组件重挂载就重复注册——这里把订阅与退订做成一对。

export type AppEventName = "auth-expired"

type Handler = () => void

const handlers = new Map<AppEventName, Set<Handler>>()

/** 返回退订函数，订阅方必须在 onUnmounted 调用 */
export function onAppEvent(name: AppEventName, handler: Handler): () => void {
  let set = handlers.get(name)
  if (!set) {
    set = new Set()
    handlers.set(name, set)
  }
  set.add(handler)
  return () => {
    set.delete(handler)
  }
}

export function emitAppEvent(name: AppEventName): void {
  const set = handlers.get(name)
  if (!set) return
  for (const handler of Array.from(set)) handler()
}
