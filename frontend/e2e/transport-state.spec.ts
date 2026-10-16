import { expect, test } from '@playwright/test'

test('加载历史会话保留支持和不支持的引用，不把未知状态当成已验证', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    const path = '/src/composables/useChat.ts'
    const { useChat } = await import(/* @vite-ignore */ path)
    const chat = useChat()
    chat.loadHistory([{ type: 'ai', content: 'saved answer', rag_trace: {
      tool_used: true, tool_name: 'search_knowledge_base', citations: [
        { source_label: 'Source 1', supported: true },
        { source_label: 'Source 9', supported: false },
        { source_label: 'Source 2' },
      ],
    } }, { type: 'ai', content: 'legacy answer', rag_trace: null }])
    return chat.messages.value.map(message => ({
      text: message.text,
      supported: message.citations.map(citation => citation.source_label),
      unsupported: message.unsupported.map(citation => citation.source_label),
    }))
  })
  expect(result).toEqual([
    { text: 'saved answer', supported: ['Source 1'], unsupported: ['Source 9'] },
    { text: 'legacy answer', supported: [], unsupported: [] },
  ])
})

test('SSE 跨字节分块支持 UTF-8、CRLF 并释放流锁', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    const path = '/src/api/sse.ts'
    const { readSse } = await import(/* @vite-ignore */ path)
    const bytes = new TextEncoder().encode('data: {"type":"content","content":"中文"}\r\n\r\ndata: [DONE]\r\n\r\n')
    const stream = new ReadableStream({ start(controller) {
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    } })
    const events = []
    await readSse(stream, event => events.push(event))
    return { events, locked: stream.locked }
  })
  expect(result.events).toEqual([{ type: 'content', content: '中文' }, { type: 'done' }])
  expect(result.locked).toBe(false)
})

test('SSE 缺少终止事件时报告中断，完成后忽略迟到帧', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    const path = '/src/api/sse.ts'
    const { readSse } = await import(/* @vite-ignore */ path)
    function stream(text) {
      return new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode(text)); controller.close() } })
    }
    let reason = ''
    try { await readSse(stream('data: {"type":"content","content":"partial"}\n\n'), () => {}) }
    catch (error) { reason = error.message }
    const events = []
    await readSse(stream('data: [DONE]\n\ndata: {"type":"content","content":"late"}\n\n'), event => events.push(event))
    return { reason, events }
  })
  expect(result.reason).toBe('stream_incomplete')
  expect(result.events).toEqual([{ type: 'done' }])
})

test('切换新会话后迟到的旧 SSE 不得写入新消息', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    const path = '/src/composables/useChat.ts'
    const { useChat } = await import(/* @vite-ignore */ path)
    const streams = []
    // 故意忽略 abort，让旧响应继续返回，检验状态层自己的隔离能力。
    globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) { streams.push(controller) } }))
    const chat = useChat()
    const first = chat.send('first')
    chat.newChat()
    const second = chat.send('second')
    for (let i = 0; i < 2; i++) {
      streams[i].enqueue(new TextEncoder().encode(`data: {"type":"content","content":"${i ? 'new' : 'old'}"}\n\ndata: [DONE]\n\n`))
      streams[i].close()
    }
    await Promise.all([first, second])
    return { messages: chat.messages.value.map(message => message.text), loading: chat.isLoading.value }
  })
  expect(result.messages).toEqual(['second', 'new'])
  expect(result.loading).toBe(false)
})

test('WS 异常中断必须释放发送状态', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    let socket
    class FakeSocket {
      static OPEN = 1
      readyState = 1
      onopen
      onmessage
      onerror
      onclose
      constructor() { socket = this }
      send() {}
      close() {}
    }
    Object.defineProperty(globalThis, 'WebSocket', { value: FakeSocket })
    const path = '/src/composables/useChat.ts'
    const { useChat } = await import(/* @vite-ignore */ path)
    const chat = useChat()
    chat.connectWs('test-only')
    socket.onopen(new Event('open'))
    await chat.send('question')
    const before = chat.isLoading.value
    socket.onerror(new Event('error'))
    return { before, after: chat.isLoading.value, thinking: chat.messages.value.at(-1).isThinking }
  })
  expect(result).toEqual({ before: true, after: false, thinking: false })
})

test('已取消的上传不得发送网络请求，非法 JSON 响应必须结束 Promise', async ({ page }) => {
  await page.goto('/login')
  const result = await page.evaluate(async () => {
    let sends = 0
    class FakeXHR {
      upload = {}
      status = 200
      responseText = '{invalid-json'
      onload
      open() {}
      setRequestHeader() {}
      send() { sends++; this.onload() }
      abort() {}
    }
    Object.defineProperty(globalThis, 'XMLHttpRequest', { value: FakeXHR })
    const path = '/src/api/http.ts'
    const { uploadFile } = await import(/* @vite-ignore */ path)
    const controller = new AbortController()
    controller.abort()
    const file = new File(['paper'], 'paper.pdf')
    const cancelled = await uploadFile('/test', file, { method: 'POST', signal: controller.signal }).catch(error => error.message)
    const before = sends
    const malformed = await uploadFile('/test', file, { method: 'POST' }).catch(error => error.message)
    return { cancelled, before, malformed, sends }
  })
  expect(result).toEqual({ cancelled: 'upload_aborted', before: 0, malformed: 'invalid_response', sends: 1 })
})
