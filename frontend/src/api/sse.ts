// SSE 分帧（`docs/rules/10-frontend-structure.md` F8）：之前 `\\n\\n` 切帧、`data: ` 前缀、`[DONE]` 字面量
// 与 JSON.parse 混在 useChat.send() 的几十行里，现在只有这里认识 SSE 语法。
import type { StreamEvent } from "./types"

/** 流的终止帧是字面量而不是 JSON（openapi.yaml: chatStream） */
const DONE_FRAME = "[DONE]"

/** 一帧里多个 data: 行按 SSE 规范用 \n 连接后再解析 */
function joinDataLines(frame: string): string {
  const lines: string[] = []
  for (const line of frame.split("\n")) {
    // 冒号开头是注释行，event:/id:/retry: 对本服务无意义，一律忽略
    if (line.startsWith("data:")) lines.push(line.slice(5).replace(/^ /, ""))
  }
  return lines.join("\n")
}

/** 解析不出 type 的帧按丢弃处理：后端随时可能加心跳帧，前端不该因此中断回答 */
export function parseStreamEvent(raw: string): StreamEvent | null {
  try {
    const value = JSON.parse(raw) as Partial<StreamEvent>
    return value && typeof value.type === "string" ? (value as StreamEvent) : null
  } catch (_) {
    return null
  }
}

export async function readSse(body: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx = buffer.indexOf("\n\n")
    while (idx !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const data = joinDataLines(frame)
      if (data && data !== DONE_FRAME) {
        const event = parseStreamEvent(data)
        if (event) onEvent(event)
      }
      idx = buffer.indexOf("\n\n")
    }
  }
}
