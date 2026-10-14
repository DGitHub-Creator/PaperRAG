<template>
  <div class="page-inner wide reader-page">
    <PageHeader icon="book-open" title-key="views.reader.title" desc-key="views.reader.desc">
      <button class="btn-secondary" disabled><Icon name="download" :size="14" />{{ $t("views.reader.export") }}</button>
    </PageHeader>

    <div class="reader-split">
      <section class="card reader-doc">
        <div class="card-head">
          <div>
            <h3>Grounded Retrieval with Verifier-in-the-Loop Citations</h3>
            <div class="sub">ACL 2025 · A. Novak, M. Lee, R. Sharma</div>
          </div>
          <span class="badge">{{ $t("views.reader.page_of", { page: 3, total: 9 }) }}</span>
        </div>
        <div class="card-body doc-body">
          <article v-for="section in sections" :key="section.id" class="doc-section" :class="{ cited: section.cited }">
            <div class="doc-section-head">
              <span class="doc-heading">{{ section.heading }}</span>
              <span class="faint">p.{{ section.page }}</span>
              <span v-if="section.cited" class="badge badge-ok">{{ $t("views.reader.cited") }}</span>
            </div>
            <p>{{ section.text }}</p>
          </article>
          <div class="doc-pager">
            <button class="btn-ghost" disabled><Icon name="chevron-right" :size="14" />{{ $t("views.reader.prev") }}</button>
            <span class="faint">3 / 9</span>
            <button class="btn-ghost" disabled>{{ $t("views.reader.next") }}<Icon name="chevron-right" :size="14" /></button>
          </div>
        </div>
      </section>

      <aside class="card reader-assistant">
        <div class="card-head">
          <h3><Icon name="message" :size="15" />{{ $t("views.reader.assistant") }}</h3>
          <span class="badge badge-warn">{{ $t("views.reader.not_evidence") }}</span>
        </div>
        <div class="card-body assistant-body">
          <div class="qa-question">{{ $t("views.reader.sample_question") }}</div>
          <div class="qa-answer">
            <p>{{ $t("views.reader.sample_answer") }}</p>
            <div class="qa-citations">
              <span class="chip"><Icon name="quote" :size="12" />p.4 §3.2</span>
              <span class="chip"><Icon name="quote" :size="12" />p.6 §4.2</span>
            </div>
          </div>

          <div class="assistant-fields">
            <dl class="kv">
              <dt>{{ $t("views.reader.field_question") }}</dt>
              <dd>{{ $t("views.reader.field_question_value") }}</dd>
              <dt>{{ $t("views.reader.field_metric") }}</dt>
              <dd>{{ $t("views.reader.field_metric_value") }}</dd>
              <dt>{{ $t("views.reader.field_limitation") }}</dt>
              <dd>{{ $t("views.reader.field_limitation_value") }}</dd>
            </dl>
          </div>
        </div>
      </aside>
    </div>

    <SampleNotice module="M7" card="P2-7 · Z3" />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue"
import SampleNotice from "../components/SampleNotice.vue"
import Icon from "../components/Icon.vue"
import { READER_SECTIONS } from "../mock/library"

const sections = READER_SECTIONS
</script>

<style scoped>
.reader-page { max-width: 1440px; }
.reader-split { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 16px; align-items: start; }
@media (max-width: 1080px) { .reader-split { grid-template-columns: minmax(0, 1fr); } }

.doc-body { padding: 0 20px; }
.doc-section { padding: 18px 0; border-bottom: 1px solid var(--border); position: relative; }
.doc-section:last-of-type { border-bottom: none; }
.doc-section.cited { padding-left: 12px; border-left: 3px solid var(--ok); background: var(--ok-soft); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.doc-section-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.doc-heading { font-weight: 600; color: var(--text-strong); font-size: 13.5px; }
.doc-section p { font-size: 13px; line-height: 1.75; color: var(--text-color); }
.doc-pager { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-top: 1px solid var(--border); }

.assistant-body { display: flex; flex-direction: column; gap: 16px; }
.qa-question { font-size: 13px; font-weight: 550; color: var(--text-strong); padding: 10px 12px; background: var(--bg-subtle); border-radius: var(--radius-sm); }
.qa-answer { font-size: 13px; line-height: 1.7; color: var(--text-color); }
.qa-citations { display: flex; gap: 6px; margin-top: 10px; }
.assistant-fields { border-top: 1px solid var(--border); padding-top: 14px; }
</style>
