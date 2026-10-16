import { Marked } from "marked"
import hljs from "highlight.js"
import katex from "katex"
import DOMPurify from "dompurify"

// 使用库自带类型与实例配置，避免修改全局解析器及用伪造类型掩盖失效选项。
const renderer = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    code(code: string, lang: string | undefined): string {
      lang = (lang || "").split(/\s/)[0]
      const language = hljs.getLanguage(lang) ? lang : "plaintext"
      return `<pre><code class="hljs language-${language}">${hljs.highlight(code, { language }).value}</code></pre>\n`
    },
  },
})

interface LatexItem {
  type: "block" | "inline"
  content: string
}

export function parseMarkdown(text: string): string {
  const latexBlocks: LatexItem[] = []
  let protectedText = text.replace(/\$\$([\s\S]*?)\$\$/g, (_match: string, formula: string) => {
    latexBlocks.push({ type: "block", content: formula.trim() })
    return `@@LATEXBLOCK${latexBlocks.length - 1}@@`
  })
  protectedText = protectedText.replace(/\$(.*?)\$/g, (_match: string, formula: string) => {
    latexBlocks.push({ type: "inline", content: formula.trim() })
    return `@@LATEXINLINE${latexBlocks.length - 1}@@`
  })
  let html = renderer.parse(protectedText, { async: false }) as string
  html = html.replace(/@@LATEXBLOCK(\d+)@@/g, (_match: string, idx: string) => {
    const item = latexBlocks[parseInt(idx)]
    if (item) {
      try {
        return katex.renderToString(item.content, { displayMode: true, throwOnError: false })
      } catch (_) { return `<pre>${item.content}</pre>` }
    }
    return `$$$$`
  })
  html = html.replace(/@@LATEXINLINE(\d+)@@/g, (_match: string, idx: string) => {
    const item = latexBlocks[parseInt(idx)]
    if (item) {
      try {
        return katex.renderToString(item.content, { displayMode: false, throwOnError: false })
      } catch (_) { return `$${item.content}$` }
    }
    return `$$`
  })
  // 模型输出、检索原文和公式均不可信；必须在所有 HTML 拼接完成后净化。
  return DOMPurify.sanitize(html)
}

export function escapeHtml(text: string): string {
  const div = document.createElement("div")
  div.textContent = text
  return div.innerHTML
}
