<template>
  <div class="page-inner wide">
    <PageHeader icon="briefcase" title-key="views.workspace.title" desc-key="views.workspace.desc">
      <button class="btn-secondary" disabled><Icon name="plus" :size="14" />{{ $t("views.workspace.new_project") }}</button>
    </PageHeader>

    <div class="split-3-1">
      <section class="card">
        <div class="card-head">
          <h3><Icon name="folder" :size="15" />{{ $t("views.workspace.board") }}</h3>
          <span class="faint">{{ $t("views.workspace.board_hint") }}</span>
        </div>
        <div class="card-body">
          <div class="kanban">
            <div v-for="col in columns" :key="col" class="kanban-col">
              <div class="kanban-col-head">
                <span>{{ $t(`views.workspace.col_${col}`) }}</span>
                <span>{{ byColumn(col).length }}</span>
              </div>
              <div v-for="task in byColumn(col)" :key="task.id" class="kanban-card">
                <div class="kc-title">{{ task.title }}</div>
                <div class="kc-sub">{{ task.module }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside class="stack">
        <div class="card">
          <div class="card-head"><h3><Icon name="users" :size="15" />{{ $t("views.workspace.projects") }}</h3></div>
          <div class="card-body stack">
            <div v-for="p in projects" :key="p.id" class="project-row">
              <div class="spread">
                <span class="project-name">{{ p.name }}</span>
                <span class="badge">{{ $t(`views.workspace.role_${p.role}`) }}</span>
              </div>
              <div class="faint">{{ $t("views.workspace.updated") }} {{ p.updated }}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3><Icon name="dollar" :size="15" />{{ $t("views.workspace.budget") }}</h3></div>
          <div class="card-body stack">
            <div v-for="line in budget" :key="line.label" class="bar-row">
              <span class="bar-label">{{ line.label }}</span>
              <div class="bar-track progress-track">
                <div class="progress-fill" :style="{ width: Math.round((line.spent / line.cap) * 100) + '%' }"></div>
              </div>
              <span class="bar-val">{{ line.spent }}/{{ line.cap }}</span>
            </div>
            <div class="faint">{{ $t("views.workspace.budget_hint") }}</div>
          </div>
        </div>
      </aside>
    </div>

    <SampleNotice module="M8" card="F-7 (proposed, 18 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { BUDGET, PROJECTS, TASKS } from "../mock/program"

const projects = PROJECTS
const budget = BUDGET
const columns = ["backlog", "reading", "analysis", "writing", "done"] as const

function byColumn(col: string) {
  return TASKS.filter((t) => t.column === col)
}
</script>

<style scoped>
.project-row { padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.project-row:last-child { border-bottom: none; }
.project-name { font-size: 13px; font-weight: 550; color: var(--text-strong); }
.bar-row .bar-label { width: 110px; }
</style>
