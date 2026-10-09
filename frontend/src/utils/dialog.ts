// 对话框的唯一出口（`docs/refactor/10` R3）：状态层不调 alert/confirm，
// 只有组件能通过这里提问，将来换成自定义对话框只改这一个文件。
export function alertDialog(message: string): void {
  window.alert(message)
}

export function confirmDialog(message: string): boolean {
  return window.confirm(message)
}
