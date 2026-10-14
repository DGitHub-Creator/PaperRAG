<template>
  <div class="page-inner wide">
    <PageHeader icon="play" title-key="views.runs.title" desc-key="views.runs.desc">
      <button class="btn-primary" disabled><Icon name="play" :size="14" />{{ $t("views.runs.start") }}</button>
    </PageHeader>

    <div class="split-2-1">
      <section class="card">
        <div class="card-head"><h3><Icon name="activity" :size="15" />{{ $t("views.runs.list") }}</h3></div>
        <table class="table">
          <thead>
            <tr>
              <th>{{ $t("views.runs.col_run") }}</th>
              <th>{{ $t("views.runs.col_status") }}</th>
              <th>{{ $t("views.runs.col_progress") }}</th>
              <th>{{ $t("views.runs.col_budget") }}</th>
              <th>{{ $t("views.runs.col_frontier") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id" :class="{ selected: run.id === activeRun.id }" @click="selected = run.id">
              <td>
                <div class="mono run-id">{{ run.id }}</div>
                <div class="faint">{{ run.goal }}</div>
              </td>
              <td><span class="badge" :class="statusClass(run.status)">{{ $t(`views.runs.status_${run.status}`) }}</span></td>
              <td class="w-progress">
                <div class="progress-track"><div class="progress-fill" :style="{ width: run.progress + '%' }"></div></div>
                <span class="faint">{{ run.progress }}%</span>
              </td>
              <td>{{ run.spent }} / {{ run.budget }} h</td>
              <td>{{ run.frontier }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <aside class="stack">
        <div class="card">
          <div class="card-head">
            <h3><Icon name="git-branch" :size="15" />{{ activeRun.id }}</h3>
            <span class="badge" :class="statusClass(activeRun.status)">{{ $t(`views.runs.status_${activeRun.status}`) }}</span>
          </div>
          <div class="card-body">
            <div class="timeline">
              <div v-for="step in steps" :key="step.id" class="timeline-item">
                <span class="timeline-dot" :class="dotClass(step.status)"></span>
                <div class="tl-title">{{ step.label }}</div>
                <div class="tl-sub">{{ step.detail }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3><Icon name="dollar" :size="15" />{{ $t("views.runs.budget") }}</h3></div>
          <div class="card-body stack">
            <div v-for="line in budget" :key="line.label" class="bar-row">
              <span class="bar-label">{{ line.label }}</span>
              <div class="bar-track progress-track">
                <div class="progress-fill" :style="{ width: Math.round((line.spent / line.cap) * 100) + '%' }"></div>
              </div>
              <span class="bar-val">{{ line.spent }}/{{ line.cap }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <SampleNotice module="M15" card="P3-1 … P3-7 (78 h)" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { BUDGET, RUNS, RUN_STEPS } from "../mock/program"
import type { MockRun } from "../mock/program"

const runs = RUNS
const steps = RUN_STEPS
const budget = BUDGET
const selected = ref(runs[0].id)

const activeRun = computed(() => runs.find((r) => r.id === selected.value) ?? runs[0])

function statusClass(status: MockRun["status"]): string {
  if (status === "running") return "badge-accent"
  if (status === "done") return "badge-ok"
  if (status === "failed") return "badge-danger"
  return "badge"
}

function dotClass(status: string): string {
  if (status === "done") return "ok"
  if (status === "run") return "run"
  return "warn"
}
</script>

<style scoped>
tbody tr { cursor: pointer; }
tbody tr.selected { background: var(--accent-soft); }
.run-id { font-weight: 600; color: var(--text-strong); }
.w-progress { min-width: 120px; }
.w-progress .progress-track { margin-bottom: 4px; }
</style>
