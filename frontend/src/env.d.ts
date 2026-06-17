/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue"
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module "marked" {
  export interface MarkedOptions {
    highlight?: (code: string, lang: string) => string
    langPrefix?: string
    breaks?: boolean
    gfm?: boolean
  }
  export function parse(src: string, options?: MarkedOptions): string
  export function setOptions(options: MarkedOptions): void
  export const marked: { parse: typeof parse; setOptions: typeof setOptions }
}

interface Window {
  __citationClick?: (index: number) => void
}
