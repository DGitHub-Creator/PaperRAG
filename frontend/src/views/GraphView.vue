<template>
  <div class="page-inner wide">
    <PageHeader icon="share" title-key="views.graph.title" desc-key="views.graph.desc">
      <button class="btn-secondary" disabled><Icon name="filter" :size="14" />{{ $t("views.graph.filter") }}</button>
    </PageHeader>

    <div class="split-2-1">
      <section class="graph-wrap">
        <svg viewBox="0 0 760 380" role="img" :aria-label="$t('views.graph.title')">
          <line
            v-for="(edge, i) in edges"
            :key="`e${i}`"
            :x1="node(edge.from).x"
            :y1="node(edge.from).y"
            :x2="node(edge.to).x"
            :y2="node(edge.to).y"
            :class="['edge', `edge-${edge.relation}`]"
          />
          <g v-for="n in nodes" :key="n.id" :class="['node', `node-${n.kind}`]">
            <circle :cx="n.x" :cy="n.y" r="7" />
            <text :x="n.x + 12" :y="n.y + 4">{{ n.label }}</text>
          </g>
        </svg>
        <div class="graph-legend">
          <span class="lg"><span class="dot dot-claim"></span>{{ $t("views.graph.kind_claim") }}</span>
          <span class="lg"><span class="dot dot-evidence"></span>{{ $t("views.graph.kind_evidence") }}</span>
          <span class="lg"><span class="dot dot-paper"></span>{{ $t("views.graph.kind_paper") }}</span>
          <span class="lg"><span class="dot dot-method"></span>{{ $t("views.graph.kind_method") }}</span>
          <span class="lg"><Icon name="alert" :size="12" />{{ $t("views.graph.relation_tension") }}</span>
        </div>
      </section>

      <aside class="card">
        <div class="card-head"><h3><Icon name="link" :size="15" />{{ $t("views.graph.registry") }}</h3></div>
        <div class="card-body stack">
          <div v-for="n in claims" :key="n.id" class="claim-row">
            <div class="claim-label">{{ n.label }}</div>
            <div class="faint">{{ $t("views.graph.evidence_linked", { count: linkedCount(n.id) }) }}</div>
          </div>
          <div class="tension">
            <Icon name="alert" :size="14" />
            <span>{{ $t("views.graph.tension_note") }}</span>
          </div>
        </div>
      </aside>
    </div>

    <SampleNotice module="M16" card="F-8 (proposed, 24 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { GRAPH_EDGES, GRAPH_NODES } from "../mock/analysis"

const nodes = GRAPH_NODES
const edges = GRAPH_EDGES
const claims = GRAPH_NODES.filter((n) => n.kind === "claim")

function node(id: string) {
  return GRAPH_NODES.find((n) => n.id === id) ?? { id: "", label: "", kind: "claim" as const, x: 0, y: 0 }
}

function linkedCount(id: string): number {
  return GRAPH_EDGES.filter((e) => e.to === id).length
}
</script>

<style scoped>
.node text { font-size: 11.5px; fill: var(--text-color); }
.node circle { stroke: #fff; stroke-width: 2; }
.node-claim circle { fill: var(--accent); }
.node-claim text { font-weight: 600; }
.node-evidence circle { fill: var(--ok); }
.node-paper circle { fill: var(--warn); }
.node-method circle { fill: var(--info); }

.edge { stroke: var(--border-strong); stroke-width: 1.5; }
.edge-tension { stroke: var(--danger); stroke-dasharray: 5 4; }
.edge-supports { stroke: var(--ok); }
.edge-invalidates { stroke: var(--danger); }

.dot-claim { background: var(--accent); }
.dot-evidence { background: var(--ok); }
.dot-paper { background: var(--warn); }
.dot-method { background: var(--info); }

.claim-row { padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.claim-row:last-of-type { border-bottom: none; }
.claim-label { font-size: 13px; font-weight: 550; color: var(--text-strong); }
.tension {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  background: var(--danger-soft);
  border: 1px solid #f7cfcf;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--danger);
}
</style>
