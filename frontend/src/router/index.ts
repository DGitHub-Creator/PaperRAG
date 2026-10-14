// 路由表（`docs/rules/10-frontend-structure.md` §7.1）：路由 name 一律取自 composables/useNav 的 NavKey。
// 五个产品入口 → 左侧分组；深链接、前进/后退、可分享 URL 都由这里承载。
// 守卫只做一件事：未登录进不了工作区，已登录不必再看登录页——判定依据是 useAuth 的 token（R2 的唯一所有者）。
import { createRouter, createWebHistory } from "vue-router"
import type { RouteRecordRaw } from "vue-router"
import { useAuth } from "../composables/useAuth"

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { titleKey: "auth.login_title", public: true },
  },
  {
    path: "/",
    component: () => import("../AppShell.vue"),
    children: [
      { path: "", redirect: { name: "chat" } },
      { path: "chat", name: "chat", component: () => import("../views/ChatView.vue"), meta: { titleKey: "views.chat.title" } },
      { path: "library", name: "library", component: () => import("../views/LibraryView.vue"), meta: { titleKey: "views.library.title" } },
      { path: "reader", name: "reader", component: () => import("../views/ReaderView.vue"), meta: { titleKey: "views.reader.title" } },
      { path: "compare", name: "compare", component: () => import("../views/CompareView.vue"), meta: { titleKey: "views.compare.title" } },
      { path: "gaps", name: "gaps", component: () => import("../views/GapsView.vue"), meta: { titleKey: "views.gaps.title" } },
      { path: "graph", name: "graph", component: () => import("../views/GraphView.vue"), meta: { titleKey: "views.graph.title" } },
      { path: "runs", name: "runs", component: () => import("../views/RunsView.vue"), meta: { titleKey: "views.runs.title" } },
      { path: "lab", name: "lab", component: () => import("../views/LabView.vue"), meta: { titleKey: "views.lab.title" } },
      { path: "writing", name: "writing", component: () => import("../views/WritingView.vue"), meta: { titleKey: "views.writing.title" } },
      { path: "radar", name: "radar", component: () => import("../views/RadarView.vue"), meta: { titleKey: "views.radar.title" } },
      { path: "history", name: "history", component: () => import("../views/HistoryView.vue"), meta: { titleKey: "views.history.title" } },
      { path: "workspace", name: "workspace", component: () => import("../views/WorkspaceView.vue"), meta: { titleKey: "views.workspace.title" } },
      { path: "settings", name: "settings", component: () => import("../views/SettingsView.vue"), meta: { titleKey: "views.settings.title" } },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: { name: "chat" } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const { token } = useAuth()
  if (to.meta.public) {
    return token.value ? { name: "chat" } : true
  }
  if (!token.value) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  return true
})

export default router
