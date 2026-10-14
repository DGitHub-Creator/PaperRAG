<template>
  <div class="page-inner">
    <PageHeader icon="pen" title-key="views.writing.title" desc-key="views.writing.desc">
      <button class="btn-secondary" disabled><Icon name="download" :size="14" />{{ $t("views.writing.export_latex") }}</button>
      <button class="btn-primary" disabled><Icon name="zap" :size="14" />{{ $t("views.writing.continue") }}</button>
    </PageHeader>

    <div class="split-1-2">
      <section class="card">
        <div class="card-head">
          <h3><Icon name="list" :size="15" />{{ $t("views.writing.outline") }}</h3>
          <span class="badge badge-warn">{{ $t("views.writing.partial") }}</span>
        </div>
        <div class="list">
          <div v-for="(sec, i) in sections" :key="sec.id" class="list-item outline-item" :class="{ active: i === activeIndex }" @click="activeIndex = i">
            <span class="outline-idx">{{ i + 1 }}</span>
            <div class="li-main">
              <div class="li-title">{{ sec.title }}</div>
              <div class="li-sub">
                <span>{{ sec.words }} {{ $t("views.writing.words") }}</span>
                <span>{{ sec.citations }} {{ $t("views.writing.citations") }}</span>
              </div>
            </div>
            <span class="badge" :class="statusClass(sec.status)">{{ $t(`views.writing.status_${sec.status}`) }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3>{{ active.title }}</h3>
          <span class="faint">{{ $t("views.writing.preview") }}</span>
        </div>
        <div class="card-body prose">
          <p>{{ $t("views.writing.preview_p1") }}</p>
          <p>
            {{ $t("views.writing.preview_p2") }}
            <span class="cited-chip"><Icon name="quote" :size="11" />p1 §3.2</span>
          </p>
          <p>{{ $t("views.writing.preview_p3") }}</p>
          <div class="grounding">
            <span class="spread">
              <span>{{ $t("views.writing.grounding") }}</span>
              <span class="faint">14 / 16</span>
            </span>
            <div class="progress-track"><div class="progress-fill" style="width: 87%"></div></div>
          </div>
        </div>
      </section>
    </div>

    <SampleNotice module="M13" card="P3-5 · F-5 (proposed, 12 h)" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { REPORT_SECTIONS } from "../mock/program"
import type { MockReportSection } from "../mock/program"

const sections = REPORT_SECTIONS
const activeIndex = ref(0)
const active = computed(() => sections[activeIndex.value])

function statusClass(status: MockReportSection["status"]): string {
  if (status === "done") return "badge-ok"
  if (status === "draft") return "badge-accent"
  return "badge"
}
</script>

<style scoped>
.outline-item { cursor: pointer; gap: 10px; }
.outline-item.active { background: var(--accent-soft); }
.outline-idx {
  width: 20px;
  height: 20px;
  flex: 0 0 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
}
.outline-item.active .outline-idx { background: var(--accent); color: #fff; }
.prose p { font-size: 13px; line-height: 1.8; color: var(--text-color); margin-bottom: 12px; }
.cited-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: var(--ok-soft);
  color: var(--ok);
  font-size: 11px;
  font-family: var(--font-mono);
  white-space: nowrap;
}
.grounding { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 12.5px; color: var(--text-muted); }
.grounding .progress-track { margin-top: 8px; }
</style>
