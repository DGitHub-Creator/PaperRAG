import hljs from "highlight.js/lib/core"
import javascript from "highlight.js/lib/languages/javascript"
import python from "highlight.js/lib/languages/python"
import bash from "highlight.js/lib/languages/bash"
import css from "highlight.js/lib/languages/css"
import xml from "highlight.js/lib/languages/xml"
import "highlight.js/styles/atom-one-light.css"
import "katex/dist/katex.min.css"

hljs.registerLanguage("javascript", javascript)
hljs.registerLanguage("python", python)
hljs.registerLanguage("bash", bash)
hljs.registerLanguage("css", css)
hljs.registerLanguage("xml", xml)

import { createApp } from "vue"
import App from "./App.vue"
import "./assets/variables.css"
import "./assets/sidebar.css"
import "./assets/chat.css"
import "./assets/history.css"
import "./assets/settings.css"
import "./assets/rag-trace.css"
import { configureRenderer } from "./utils/markdown"
import i18n from "./i18n"

configureRenderer()
createApp(App).use(i18n).mount("#app")
