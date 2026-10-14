<template>
  <div class="page-inner">
    <PageHeader icon="rss" title-key="views.radar.title" desc-key="views.radar.desc">
      <button class="btn-secondary" disabled><Icon name="refresh" :size="14" />{{ $t("views.radar.rescan") }}</button>
    </PageHeader>

    <div class="grid grid-4 radar-stats">
      <div v-for="kind in kinds" :key="kind" class="stat">
        <div class="stat-label">{{ $t(`views.radar.kind_${kind}`) }}</div>
        <div class="stat-value">{{ countKind(kind) }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3><Icon name="trending" :size="15" />{{ $t("views.radar.diffs") }}</h3>
        <span class="faint">{{ $t("views.radar.window_hint") }}</span>
      </div>
      <div class="list">
        <div v-for="diff in diffs" :key="diff.id" class="list-item">
          <span class="badge" :class="kindClass(diff.kind)">{{ $t(`views.radar.kind_${diff.kind}`) }}</span>
          <div class="li-main">
            <div class="li-title">{{ diff.paper }}</div>
            <div class="li-sub"><span>{{ diff.summary }}</span></div>
          </div>
          <span class="faint">{{ diff.when }}</span>
        </div>
      </div>
    </div>

    <SampleNotice module="M14" card="F-4 (proposed, 14 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { RADAR_DIFFS } from "../mock/program"
import type { MockRadarDiff } from "../mock/program"

const diffs = RADAR_DIFFS
const kinds = ["new", "extends", "contradicts", "retracted"] as const

function countKind(kind: string): number {
  return diffs.filter((d) => d.kind === kind).length
}

function kindClass(kind: MockRadarDiff["kind"]): string {
  if (kind === "new") return "badge-info"
  if (kind === "extends") return "badge-ok"
  if (kind === "contradicts") return "badge-warn"
  return "badge-danger"
}
</script>

<style scoped>
.radar-stats { margin-bottom: 18px; }
</style>
