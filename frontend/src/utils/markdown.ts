import { parse, setOptions } from "marked"
import hljs from "highlight.js"
import katex from "katex"

export function configureRenderer(): void {
  setOptions({
    highlight(code: string, lang: string): string {
      const language = hljs.getLanguage(lang) ? lang : "plaintext"
      return hljs.highlight(code, { language }).value
    },
    langPrefix: "hljs language-",
    breaks: true,
    gfm: true,
  })
}

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
  let html: string = parse(protectedText)
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
  return html
}

export function escapeHtml(text: string): string {
  const div = document.createElement("div")
  div.textContent = text
  return div.innerHTML
}
