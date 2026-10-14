<template>
  <svg
    class="rp-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    :width="size"
    :height="size"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from "vue"

// 内联 SVG 图标集：仓库没有引 Font Awesome，也没有网络可用，
// 所以图标自带（24×24 / stroke 风格），避免"图标全空"这种只有联网才发现的缺陷。
const props = withDefaults(defineProps<{ name: string; size?: number; strokeWidth?: number }>(), {
  size: 16,
  strokeWidth: 1.8,
})

/** 圆 → 两段圆弧的 path，保持每个图标都是同一种节点（path），模板不用分支 */
function circle(cx: number, cy: number, r: number): string {
  return `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`
}

const ICONS: Record<string, string[]> = {
  message: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  book: ["M4 19.5A2.5 2.5 0 0 1 6.5 17H20", "M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"],
  "book-open": ["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z", "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"],
  columns: ["M3 3h18v18H3z", "M12 3v18"],
  bulb: ["M9 18h6", "M10 22h4", "M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"],
  share: [circle(18, 5, 3), circle(6, 12, 3), circle(18, 19, 3), "M8.59 13.51l6.83 3.98", "M15.41 6.51l-6.82 3.98"],
  play: [circle(12, 12, 10), "M10 8l6 4-6 4z"],
  flask: ["M10 2v6.5L4.7 17.8A2 2 0 0 0 6.4 21h11.2a2 2 0 0 0 1.7-3.2L14 8.5V2", "M8.5 2h7", "M7.5 15h9"],
  pen: ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"],
  rss: [circle(5, 19, 1), "M4 11a9 9 0 0 1 9 9", "M4 4a16 16 0 0 1 16 16"],
  clock: [circle(12, 12, 10), "M12 7v5l3.5 2"],
  briefcase: ["M4 7h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z", "M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2", "M3 12h18"],
  sliders: ["M4 21v-7", "M4 10V3", "M12 21v-9", "M12 8V3", "M20 21v-5", "M20 12V3", "M1 14h6", "M9 8h6", "M17 16h6"],
  globe: [circle(12, 12, 10), "M2 12h20", "M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
  trash: ["M3 6h18", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2", "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6", "M10 11v6", "M14 11v6"],
  plus: ["M12 5v14", "M5 12h14"],
  more: [circle(5, 12, 1), circle(12, 12, 1), circle(19, 12, 1)],
  search: [circle(11, 11, 8), "M21 21l-4.3-4.3"],
  refresh: ["M23 4v6h-6", "M20.5 15a9 9 0 1 1-2.1-9.4L23 10"],
  check: ["M20 6L9 17l-5-5"],
  x: ["M18 6L6 18", "M6 6l12 12"],
  alert: ["M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4", "M12 17h.01"],
  info: [circle(12, 12, 10), "M12 16v-4", "M12 8h.01"],
  upload: ["M16 16l-4-4-4 4", "M12 12v9", "M20.4 18.4A5 5 0 0 0 18 9h-1.3A8 8 0 1 0 3 16.3"],
  file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"],
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
  paperclip: ["M21.4 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"],
  send: ["M22 2L11 13", "M22 2l-7 20-4-9-9-4z"],
  stop: ["M7 7h10v10H7z"],
  "chevron-down": ["M6 9l6 6 6-6"],
  "chevron-right": ["M9 18l6-6-6-6"],
  external: ["M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6", "M15 3h6v6", "M10 14L21 3"],
  target: [circle(12, 12, 10), circle(12, 12, 6), circle(12, 12, 2)],
  layers: ["M12 2L2 7l10 5 10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
  cpu: ["M4 4h16v16H4z", "M9 9h6v6H9z", "M9 1v3", "M15 1v3", "M9 20v3", "M15 20v3", "M20 9h3", "M20 14h3", "M1 9h3", "M1 14h3"],
  filter: ["M22 3H2l8 9.5V19l4 2v-8.5z"],
  calendar: ["M4 5h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z", "M16 3v4", "M8 3v4", "M3 11h18"],
  star: ["M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14l-5-4.87 6.91-1.01z"],
  tag: ["M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z", "M7 7h.01"],
  link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
  zap: ["M13 2L3 14h9l-1 8 10-12h-9z"],
  "git-branch": [circle(6, 6, 3), circle(6, 18, 3), circle(18, 6, 3), "M6 9v6", "M18 9v1a3 3 0 0 1-3 3H9"],
  activity: ["M22 12h-4l-3 9L9 3l-3 9H2"],
  database: ["M12 2C7 2 3 3.8 3 6s4 4 9 4 9-1.8 9-4-4-4-9-4z", "M3 6v6c0 2.2 4 4 9 4s9-1.8 9-4V6", "M3 12v6c0 2.2 4 4 9 4s9-1.8 9-4v-6"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"],
  users: ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2", circle(9, 7, 4), "M23 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
  dollar: ["M12 1v22", "M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"],
  folder: ["M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"],
  list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  eye: ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", circle(12, 12, 3)],
  flag: ["M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z", "M4 22v-7"],
  trending: ["M23 6l-9.5 9.5-5-5L1 18", "M17 6h6v6"],
  inbox: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"],
  quote: ["M6 17h3l2-4V7H5v6h3z", "M15 17h3l2-4V7h-6v6h3z"],
  dot: [circle(12, 12, 3)],
}

const paths = computed<string[]>(() => ICONS[props.name] ?? ICONS.dot)
</script>

<style scoped>
.rp-icon {
  display: inline-block;
  flex: 0 0 auto;
  vertical-align: -0.15em;
}
</style>
