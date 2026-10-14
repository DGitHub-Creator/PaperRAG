<template>
  <div class="page-inner wide">
    <PageHeader icon="bulb" title-key="views.gaps.title" desc-key="views.gaps.desc">
      <button class="btn-secondary" disabled><Icon name="refresh" :size="14" />{{ $t("views.gaps.rescan") }}</button>
    </PageHeader>

    <div class="grid grid-2">
      <section class="stack">
        <div class="card">
          <div class="card-head"><h3><Icon name="target" :size="15" />{{ $t("views.gaps.candidates") }}</h3></div>
          <div class="card-body stack">
            <div v-for="gap in gaps" :key="gap.id" class="gap-item">
              <div class="spread">
                <span class="gap-title">{{ gap.title }}</span>
                <span class="badge" :class="statusClass(gap.status)">{{ $t(`views.gaps.status_${gap.status}`) }}</span>
              </div>
              <div class="bar-row">
                <span class="bar-label">{{ $t("views.gaps.support") }}</span>
                <div class="bar-track progress-track">
                  <div class="progress-fill" :style="{ width: Math.round(gap.support * 100) + '%' }"></div>
                </div>
                <span class="bar-val">{{ Math.round(gap.support * 100) }}%</span>
              </div>
              <div class="gap-note">{{ gap.note }}</div>
              <div class="faint">{{ $t("views.gaps.evidence_count", { count: gap.evidenceCount }) }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3><Icon name="flag" :size="15" />{{ $t("views.gaps.board") }}</h3>
          <span class="faint">{{ $t("views.gaps.board_hint") }}</span>
        </div>
        <div class="card-body">
          <div class="kanban board">
            <div v-for="col in frontiers" :key="col" class="kanban-col">
              <div class="kanban-col-head">
                <span>{{ $t(`views.gaps.frontier_${col}`) }}</span>
                <span>{{ byFrontier(col).length }}</span>
              </div>
              <div v-for="h in byFrontier(col)" :key="h.id" class="kanban-card">
                <div class="kc-title">{{ h.statement }}</div>
                <div class="kc-tags">
                  <span class="chip"><Icon name="dollar" :size="11" />{{ h.cost }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <SampleNotice module="M11" card="F-2 (proposed, 20 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { GAPS, HYPOTHESES } from "../mock/analysis"
import type { MockGap } from "../mock/analysis"

const gaps = GAPS
const frontiers = ["explore", "test", "refine", "parked"] as const

function byFrontier(col: string) {
  return HYPOTHESES.filter((h) => h.frontier === col)
}

function statusClass(status: MockGap["status"]): string {
  if (status === "backed") return "badge-ok"
  if (status === "rejected") return "badge-danger"
  return "badge-info"
}
</script>

<style scoped>
.gap-item { padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.gap-item:last-child { padding-bottom: 0; border-bottom: none; }
.gap-title { font-size: 13px; font-weight: 550; color: var(--text-strong); }
.gap-note { font-size: 12px; color: var(--text-muted); }
.board { grid-template-columns: repeat(4, minmax(0, 1fr)); }
</style>
