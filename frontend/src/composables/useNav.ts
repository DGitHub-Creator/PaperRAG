// 导航模型（`docs/rules/10-frontend-structure.md` §2/R10）：NavKey 是**路由名的联合类型**，
// 路由表的 name 与本文件同源；本文件不再持有视图状态——视图状态已交给 vue-router（10 §7.1）。
// ⚠️ NavKey 必须写在一行：check_frontend.py 只取该声明的首行。

export type NavKey = "chat" | "library" | "reader" | "compare" | "gaps" | "graph" | "runs" | "lab" | "writing" | "radar" | "history" | "workspace" | "settings"

export interface NavItem {
  key: NavKey
  /** Icon.vue 的图标名 */
  icon: string
  /** 右侧小徽标（可选）：值为 i18n 键 */
  badgeKey?: string
}

export interface NavGroup {
  labelKey: string
  items: NavItem[]
}

/** 左竖栏的分组模型：分组对应 docs/rules/10 §7.1 的路由表，顺序即展示顺序。 */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.groups.research",
    items: [
      { key: "chat", icon: "message" },
      { key: "library", icon: "book" },
      { key: "reader", icon: "book-open" },
    ],
  },
  {
    labelKey: "nav.groups.analysis",
    items: [
      { key: "compare", icon: "columns", badgeKey: "nav.badge.sample" },
      { key: "gaps", icon: "bulb", badgeKey: "nav.badge.sample" },
      { key: "graph", icon: "share", badgeKey: "nav.badge.sample" },
    ],
  },
  {
    labelKey: "nav.groups.runs",
    items: [
      { key: "runs", icon: "play", badgeKey: "nav.badge.sample" },
      { key: "lab", icon: "flask", badgeKey: "nav.badge.sample" },
    ],
  },
  {
    labelKey: "nav.groups.output",
    items: [
      { key: "writing", icon: "pen", badgeKey: "nav.badge.sample" },
      { key: "radar", icon: "rss", badgeKey: "nav.badge.sample" },
      { key: "history", icon: "clock" },
    ],
  },
  {
    labelKey: "nav.groups.manage",
    items: [
      { key: "workspace", icon: "briefcase", badgeKey: "nav.badge.sample" },
      { key: "settings", icon: "sliders" },
    ],
  },
]
