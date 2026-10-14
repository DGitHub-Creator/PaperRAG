<template>
  <div class="page-inner wide">
    <PageHeader icon="book" title-key="views.library.title" desc-key="views.library.desc">
      <button class="btn-secondary" @click="reload"><Icon name="refresh" :size="14" />{{ $t("settings.refresh") }}</button>
      <button class="btn-primary" disabled><Icon name="plus" :size="14" />{{ $t("views.library.add_paper") }}</button>
    </PageHeader>

    <div class="grid grid-3 stats-row">
      <div class="stat">
        <div class="stat-label">{{ $t("views.library.stat_documents") }}</div>
        <div class="stat-value">{{ documents.length }}</div>
        <div class="stat-hint">{{ $t("views.library.stat_documents_hint") }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">{{ $t("views.library.stat_chunks") }}</div>
        <div class="stat-value">{{ totalChunks }}</div>
        <div class="stat-hint">{{ $t("views.library.stat_chunks_hint") }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">{{ $t("views.library.stat_topics") }}</div>
        <div class="stat-value">{{ topics.length }}</div>
        <div class="stat-hint">{{ $t("views.library.stat_topics_hint") }}</div>
      </div>
    </div>

    <div class="tabs library-tabs">
      <button v-for="tab in tabs" :key="tab" :class="['tab', { active: active === tab }]" @click="active = tab">
        {{ $t(`views.library.tab_${tab}`) }}
      </button>
    </div>

    <section v-if="active === 'papers'" class="card">
      <div v-if="isLoading" class="empty-state"><span class="spinner"></span></div>
      <div v-else-if="!documents.length" class="empty-state">
        <Icon name="inbox" :size="26" /><span>{{ $t("settings.empty_documents") }}</span>
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>{{ $t("views.library.col_title") }}</th>
            <th>{{ $t("views.library.col_type") }}</th>
            <th>{{ $t("views.library.col_chunks") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in documents" :key="doc.filename">
            <td>
              <div class="paper-title">{{ doc.filename }}</div>
              <div class="faint mono">{{ $t("views.library.local_file") }}</div>
            </td>
            <td><span class="badge">{{ doc.file_type }}</span></td>
            <td>{{ doc.chunk_count }}</td>
            <td class="row-end">
              <RouterLink class="btn-ghost" :to="{ name: 'reader' }">
                <Icon name="book-open" :size="14" />{{ $t("views.library.open_reader") }}
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-else-if="active === 'topics'" class="grid grid-2">
      <div v-for="topic in topics" :key="topic.id" class="card topic-card">
        <div class="card-head">
          <div>
            <h3>{{ topic.name }}</h3>
            <div class="sub">{{ topic.count }} {{ $t("views.library.papers_count") }}</div>
          </div>
          <Icon name="layers" :size="16" />
        </div>
        <div class="card-body chip-row">
          <span v-for="kw in topic.keywords" :key="kw" class="chip">{{ kw }}</span>
        </div>
      </div>
    </section>

    <section v-else class="card">
      <table class="table">
        <thead>
          <tr>
            <th>{{ $t("views.library.col_source") }}</th>
            <th>{{ $t("views.library.col_query") }}</th>
            <th>{{ $t("views.library.col_cadence") }}</th>
            <th>{{ $t("views.library.col_last_run") }}</th>
            <th>{{ $t("views.library.col_new") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="src in crawlSources" :key="src.id">
            <td><span class="badge badge-accent">{{ src.kind }}</span></td>
            <td class="mono">{{ src.query }}</td>
            <td>{{ src.cadence }}</td>
            <td class="faint">{{ src.lastRun }}</td>
            <td>{{ src.newItems }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <SampleNotice module="M1 · M2 · M9" card="P1-3 · P2-9 · P2-10" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { useDocuments } from "../composables/useDocuments"
import { TOPICS, CRAWL_SOURCES } from "../mock/library"

const { documents, isLoading, refresh } = useDocuments()

const topics = TOPICS
const crawlSources = CRAWL_SOURCES
const tabs = ["papers", "topics", "crawl"] as const
const active = ref<(typeof tabs)[number]>("papers")

const totalChunks = computed(() => documents.value.reduce((sum, doc) => sum + doc.chunk_count, 0))

onMounted(() => { void reload() })

async function reload(): Promise<void> {
  try {
    await refresh()
  } catch {
    // 文档列表的真实错误路径由设置页负责展示；书架页拿到空列表即可，不重复弹窗
  }
}
</script>

<style scoped>
.stats-row { margin-bottom: 18px; }
.library-tabs { margin-bottom: 16px; }
.paper-title { font-weight: 550; color: var(--text-strong); }
.row-end { text-align: right; }
.topic-card :deep(.card-head) { color: var(--text-muted); }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
