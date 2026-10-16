// SSE 分帧（`docs/rules/10-frontend-structure.md` F8）：之前 `\\n\\n` 切帧、`data: ` 前缀、`[DONE]` 字面量
// 与 JSON.parse 混在 useChat.send() 的几十行里，现在只有这里认识 SSE 语法。
import type { StreamEvent } from "./types"
import { ApiError } from "./http"

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
  const maxFrameChars = 4 * 1024 * 1024
  let buffer = ""
  try {
    for (;;) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      // 在拼接后处理 CRLF，兼容换行符恰好跨网络分块。
      buffer = buffer.replace(/\r\n/g, "\n")
      let idx = buffer.indexOf("\n\n")
      while (idx !== -1) {
        if (idx > maxFrameChars) throw new ApiError(0, "stream_frame_too_large")
        const data = joinDataLines(buffer.slice(0, idx))
        buffer = buffer.slice(idx + 2)
        if (data === DONE_FRAME) {
          onEvent({ type: "done" })
          return
        }
        if (data) {
          const event = parseStreamEvent(data)
          if (event) {
            onEvent(event)
            if (event.type === "error" || event.type === "done") return
          }
        }
        idx = buffer.indexOf("\n\n")
      }
      if (buffer.length > maxFrameChars) throw new ApiError(0, "stream_frame_too_large")
      if (done) throw new ApiError(0, "stream_incomplete")
    }
  } finally {
    try { await reader.cancel() }
    finally { reader.releaseLock() }
  }
}
