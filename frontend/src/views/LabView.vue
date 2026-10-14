<template>
  <div class="page-inner">
    <PageHeader icon="flask" title-key="views.lab.title" desc-key="views.lab.desc">
      <button class="btn-primary" disabled><Icon name="plus" :size="14" />{{ $t("views.lab.new_experiment") }}</button>
    </PageHeader>

    <div class="split-1-2">
      <section class="card">
        <div class="card-head"><h3><Icon name="cpu" :size="15" />{{ $t("views.lab.tools") }}</h3></div>
        <div class="card-body stack">
          <div v-for="tool in tools" :key="tool.name" class="tool-row">
            <div class="spread">
              <span class="tool-name">{{ tool.name }}</span>
              <span class="badge" :class="tool.ok ? 'badge-ok' : 'badge-warn'">{{ tool.ok ? $t("views.lab.available") : $t("views.lab.missing") }}</span>
            </div>
            <div class="faint mono">{{ tool.note }}</div>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3><Icon name="flask" :size="15" />{{ $t("views.lab.experiments") }}</h3>
          <span class="faint">{{ $t("views.lab.artifacts_hint") }}</span>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>{{ $t("views.lab.col_name") }}</th>
              <th>{{ $t("views.lab.col_tool") }}</th>
              <th>{{ $t("views.lab.col_status") }}</th>
              <th>{{ $t("views.lab.col_artifact") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="exp in experiments" :key="exp.id">
              <td class="exp-name">{{ exp.name }}</td>
              <td><span class="chip">{{ exp.tool }}</span></td>
              <td><span class="badge" :class="statusClass(exp.status)">{{ $t(`views.lab.status_${exp.status}`) }}</span></td>
              <td class="mono faint">{{ exp.artifact }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <SampleNotice module="M12" card="F-3 (proposed, 24 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { LAB_EXPERIMENTS } from "../mock/program"
import type { MockLabExperiment } from "../mock/program"

const experiments = LAB_EXPERIMENTS

const tools = [
  { name: "python", ok: true, note: "3.12 · numpy / pandas" },
  { name: "model checker", ok: false, note: "not installed" },
  { name: "plotting", ok: true, note: "matplotlib" },
]

function statusClass(status: MockLabExperiment["status"]): string {
  if (status === "verified") return "badge-ok"
  if (status === "running") return "badge-accent"
  if (status === "invalid") return "badge-danger"
  return "badge"
}
</script>

<style scoped>
.tool-row { padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.tool-row:last-child { border-bottom: none; }
.tool-name { font-size: 13px; font-weight: 550; color: var(--text-strong); }
.exp-name { font-weight: 550; color: var(--text-strong); }
</style>
