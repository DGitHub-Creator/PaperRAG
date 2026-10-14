<template>
  <div class="page-inner wide">
    <PageHeader icon="columns" title-key="views.compare.title" desc-key="views.compare.desc">
      <button class="btn-secondary" disabled><Icon name="plus" :size="14" />{{ $t("views.compare.add_paper") }}</button>
      <button class="btn-primary" disabled><Icon name="download" :size="14" />{{ $t("views.compare.export") }}</button>
    </PageHeader>

    <div class="page-toolbar">
      <div class="row wrap">
        <span class="chip"><Icon name="columns" :size="12" />{{ $t("views.compare.dimensions", { count: rows.length }) }}</span>
        <span class="chip"><Icon name="book" :size="12" />{{ $t("views.compare.papers", { count: columns.length }) }}</span>
      </div>
      <div class="faint">{{ $t("views.compare.edit_hint") }}</div>
    </div>

    <div class="card compare-card">
      <table class="table matrix-table">
        <thead>
          <tr>
            <th class="dim-col">{{ $t("views.compare.col_dimension") }}</th>
            <th v-for="col in columns" :key="col.id">
              <div class="col-title">{{ col.label }}</div>
              <div class="col-sub">{{ col.venue }} · {{ col.year }}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.dimension">
            <td class="dim">{{ row.dimension }}</td>
            <td v-for="(value, i) in row.values" :key="i">{{ value }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <SampleNotice module="M10" card="F-1 (proposed, 16 h)" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { MATRIX_COLUMNS, MATRIX_ROWS } from "../mock/analysis"

const columns = MATRIX_COLUMNS
const rows = MATRIX_ROWS
</script>

<style scoped>
.compare-card { overflow-x: auto; }
.matrix-table { min-width: 760px; }
.matrix-table .dim-col { min-width: 150px; }
.matrix-table .dim { font-weight: 600; color: var(--text-strong); white-space: nowrap; background: var(--bg-subtle); }
.col-title { color: var(--text-strong); font-size: 12.5px; text-transform: none; letter-spacing: 0; }
.col-sub { color: var(--text-faint); font-size: 11px; font-weight: 400; margin-top: 2px; }
</style>
