# 05 — PostgreSQL Schema 收编与 Chunk 数据重建

> 对应决策 Q4、Q5。原则：**先核查、后建基线、禁止对存量库重复初始化建表**；Milvus 降级为可重建索引，PostgreSQL 成为文献与分块正文的唯一真相（02 §0 L3）。

## 1. 收编前置核查（必须在任何写操作之前完成）

存量库不可信任：`init_db()` 在 alembic 失败时静默回退 `Base.metadata.create_all`（`core/database.py:99-120`），所以**库可能物理存在 9 张表但没有任何 `alembic_version` 行**。

核查脚本 `scripts/audit_schema.py`（A0-3 交付，只读）：

| 检查 | 方法 | 判定 |
| --- | --- | --- |
| 实际表集合 | `information_schema.tables WHERE table_schema='public'` | 与 `models.py` 声明的 9 表 diff |
| 迁移版本 | `SELECT version_num FROM alembic_version`（表不存在 = 曾走 create_all） | 三种情形：无表 / 空 / head 不符 |
| 列级漂移 | `information_schema.columns` vs SQLAlchemy `Base.metadata`（类型、可空、server_default） | 逐字段 diff 报告 |
| 索引与约束 | `pg_indexes` + `pg_constraint` | 已知漂移：`ix_paper_nodes_id` 缺失；`filename` 是唯一索引而非 UNIQUE 约束（sqlc 经 `constraint_type='u'` 查不到） |
| 数据体量 | 每表 `count(*)`、时间列 `min/max` | 决定迁移是否可在线执行 |
| 时区真相 | 见 §4 | 决定 TIMESTAMPTZ 转换方式 |

**产出**：`docs/refactor/schema-baseline.json`（结构快照，进仓库）。Go 的迁移基线由此生成，**不由 ORM 直接生成**。

## 2. 冻结 alembic，建立 golang-migrate 基线

> **迁移文件形态**：`server/migrations/*.sql` 是纯 SQL + `migrate` 约定的 `.down.sql`，**不需要任何 Go 代码即可执行**（用 `migrate/migrate` 镜像或 CLI：`docker run --rm migrate/migrate -path /migrations -database "$DATABASE_URL" up`）。因此 Milestone A0 可以在 Go 服务还不存在时就按同一套迁移文件建表，而不必回头再引入第二套迁移工具。

| 步骤 | 动作 | 约束 |
| --- | --- | --- |
| 2.1 | 停用 `init_db()` 的 alembic 调用与 `create_all` 兜底 | 改为：探测 schema 与基线不符 → **记录差异并抛出启动失败**（禁止任何隐式建表）。对应决策 Q4「删除静默兜底，改为明确报错」 |
| 2.2 | 生成 `server/migrations/000001_baseline.{up,down}.sql` | 内容 = §1 核查出的**实际结构**（不是 ORM 声明），含现存 9 表 + 索引 + 约束 |
| 2.3 | 存量库打基线戳 | `migrate version 1`（只写 `schema_migrations`，不执行 DDL）；新库走 `000001_baseline.up.sql` |
| 2.4 | `alembic/` 保留为只读历史 | 在 `alembic/README` 与 CI 中标注 FROZEN；禁止新增 revision。`models.py` 继续用于 Python 侧 ORM 读，但**不再作为 schema 来源** |
| 2.5 | 漂移修复作为第一个后续迁移 | `000002_fix_drift`：补 `ix_paper_nodes_id`；`paper_nodes.filename` 唯一索引转 UNIQUE 约束（**先核查是否与现网语义等价**，等价则记为"不改"，避免无收益 DDL） |

**幂等纪律**：所有迁移可重复执行安全检查；`down` 必须真实可回退，禁止 `down` 里写 `DROP TABLE IF EXISTS` 掩盖问题。

## 3. Chunk 可信化：新表设计

现状问题（03 §2）：叶子块正文只在 Milvus 且 `VARCHAR(2000)` 截断；`parent_chunks` 只收 level 1/2 而 PDF 默认路径不产 → 实际近空；无版本、无定位、无哈希。

新增（`server/migrations/000003_paper_chunks.sql`，A0-4 交付；DDL 由 Go 侧迁移文件持有，Python 同期加 SQLAlchemy 映射读取）：

```sql
CREATE TABLE papers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id integer REFERENCES users(id) ON DELETE CASCADE,
  workspace_id integer REFERENCES workspaces(id) ON DELETE SET NULL,
  display_name text NOT NULL,            -- 上传时的文件名，非唯一键
  title text, doi text, arxiv_id text, corpus_name text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX papers_doi_key ON papers(doi) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX papers_arxiv_key ON papers(arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE UNIQUE INDEX papers_owner_display_key ON papers(owner_id, display_name) WHERE owner_id IS NOT NULL;

CREATE TABLE paper_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  version_no integer NOT NULL,
  raw_sha256 text NOT NULL,               -- 原始 PDF 字节哈希，去重与完整性锚点
  parser text, parse_state text NOT NULL DEFAULT 'pending',   -- pending|running|succeeded|failed
  index_state text NOT NULL DEFAULT 'none',                   -- none|building|ready|stale|failed
  index_error text, size_bytes bigint,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (paper_id, version_no), UNIQUE (paper_id, raw_sha256)
);

CREATE TABLE paper_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_version_id uuid NOT NULL REFERENCES paper_versions(id) ON DELETE CASCADE,
  role text NOT NULL,                     -- raw_pdf|parsed_markdown|figures_manifest
  object_id text NOT NULL,                -- ObjectStorage 抽象，不存服务端绝对路径
  mime text, sha256 text, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (paper_version_id, role)
);

CREATE TABLE paper_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_version_id uuid NOT NULL REFERENCES paper_versions(id) ON DELETE CASCADE,
  parent_section_id uuid REFERENCES paper_sections(id) ON DELETE CASCADE,
  level smallint NOT NULL, heading text NOT NULL,
  chapter_path text NOT NULL,             -- "方法 → 3.1 定理"
  ordinal integer NOT NULL, start_char integer, end_char integer,
  UNIQUE (paper_version_id, level, ordinal)
);

CREATE TABLE paper_chunks (
  chunk_id text PRIMARY KEY,              -- 见 §3.1 稳定 ID 规则
  paper_version_id uuid NOT NULL REFERENCES paper_versions(id) ON DELETE CASCADE,
  section_id uuid REFERENCES paper_sections(id) ON DELETE SET NULL,
  level smallint NOT NULL,                -- 1=章级 2=段级 3=叶级（沿用现实现数值，见 §3.3）
  ordinal integer NOT NULL,
  parent_chunk_id text REFERENCES paper_chunks(chunk_id) ON DELETE CASCADE,
  root_chunk_id text,
  text text NOT NULL,                     -- 完整正文，无 2000 截断
  content_hash text NOT NULL,             -- sha256(normalized text)
  page_number integer NOT NULL DEFAULT 0, -- 无法定位时为 0 并显式标记
  page_is_exact boolean NOT NULL DEFAULT false,
  start_char integer, end_char integer,   -- 相对 normalized full text
  token_count integer,
  chapter_path text NOT NULL DEFAULT '',
  has_formula boolean NOT NULL DEFAULT false, formulas jsonb NOT NULL DEFAULT '[]',
  has_citation boolean NOT NULL DEFAULT false, citations jsonb NOT NULL DEFAULT '[]',
  has_glossary boolean NOT NULL DEFAULT false, glossary_terms jsonb NOT NULL DEFAULT '[]',
  has_theorem boolean NOT NULL DEFAULT false, has_proof boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (paper_version_id, level, ordinal)
);
CREATE INDEX paper_chunks_version_idx ON paper_chunks(paper_version_id);
CREATE INDEX paper_chunks_parent_idx ON paper_chunks(parent_chunk_id);
CREATE INDEX paper_chunks_hash_idx ON paper_chunks(content_hash);
CREATE INDEX paper_chunks_formulas_gin ON paper_chunks USING gin (formulas jsonb_path_ops);

CREATE TABLE paper_chunk_vectors (
  chunk_id text PRIMARY KEY REFERENCES paper_chunks(chunk_id) ON DELETE CASCADE,
  collection text NOT NULL, milvus_id bigint, dim integer NOT NULL,
  embedded_at timestamptz NOT NULL, index_state text NOT NULL, error text
);
```

### 3.1 稳定 ID 规则

```
chunk_id  = "{paper_version_id}:{level}:{ordinal:06d}"
```

**可确定性重算** ⇒ 重解析同版本得到同一批 ID，`INSERT ... ON CONFLICT (paper_version_id, level, ordinal) DO UPDATE` 天然幂等。`content_hash` 用于判断正文是否真的变了（变了才需要重嵌入）。

> 现状 ID 不可靠：`document_loader.py:550` 用 `f"{filename}_p{p_idx}_c{c_idx}"`，重名文件即冲突，且不随版本变化。旧 ID 在重建时保留为 `legacy_chunk_id` 列（迁移脚本内映射表），供已存的 `chat_messages.rag_trace` 历史引用不失效。

### 3.2 各层职责重新划分

| 存储 | 存什么 | 明确不存 |
| --- | --- | --- |
| PostgreSQL | 文献实体、版本、文件引用、章节、**全部层级 chunk 正文 + 定位 + 元数据**、索引状态台账 | 向量 |
| Milvus | `chunk_id` + dense + sparse + 少量过滤字段（`level`、`has_theorem_in_parent`、`page_number`、`filename`） | **正文不再是唯一真相**；`text` 字段改为截断存展示用，读取一律回 PG |
| Redis | 缓存（父块读取、会话、限流） | 任何唯一真相 |
| 文件 | `ingested.json`、`bm25_state.json` → 迁移为 `papers`/`paper_versions` 行 + `paper_files.object_id` | — |

### 3.3 层级数值语义（修 G18）

**以 `document_loader.py` 的实现为准**：`1=章级、2=段级、3=叶级`，检索过滤 `chunk_level==3`（`rag_utils.py:727`）。`models.py:207-210` 的 docstring（0=叶）**是错的**，A0 内改正而非改代码。新表列名改为 `level` 避免与旧 `chunk_level` 混淆，迁移注释里写死数值含义。

### 3.4 `parent_chunks` 的结局

`ParentChunkStore`（`rag/parent_chunk_store.py`）改为读写 `paper_chunks`（`level IN (1,2)`），Redis Cache-Aside 逻辑不变；`parent_chunks` 表在里程碑 A 的阶段 3 之后 DROP（届时它仍近乎空，无数据搬迁成本）。**A0 不删表**，保证 Python 检索路径随时可回退。

## 4. TIMESTAMPTZ 统一（决策 Q4：先验证再转换）

现状：所有列为 `timestamp without time zone`；写入混用 naive `datetime.utcnow()`（`conversation_storage.py:85`、`models.py` 各默认值）与 aware `datetime.now(UTC)`（`parent_chunk_store.py:95`）。aware 值经 psycopg2 落到 `timestamp` 列时，**PG 会按会话 `TimeZone` 转换后再丢弃偏移** → 存量数值的真实语义取决于历史会话时区与 `log_timezone`，**不能假定为 UTC**。

### 4.1 验证（只读，A0-3）

```sql
SHOW timezone;  SHOW log_timezone;  -- 以及 server_version
```

1. **探针法**：写入一行已知 UTC 时刻（`INSERT ... VALUES (now() AT TIME ZONE 'UTC')` 与 `datetime.now(UTC)` 两条路径各一），用 `SELECT col, extract(epoch from col)` 读回，比较与真实 epoch 的偏移 → 得到"写入路径 × 会话时区 → 落库语义"的映射。
2. **分布法**：对 `users.created_at`、`chat_messages.timestamp` 做小时直方图。若峰值集中在 UTC 工作时段之外 8 小时（+08:00 特征），说明落库值是本地时间；与运维记录/已知事件时刻交叉验证。
3. **交叉法**：同一会话内 `chat_messages.timestamp` 与该行 `id` 递增顺序（serial 单调）应单调不减；违例数量指示混用规模。

**结论写入** `docs/refactor/timestamp-audit.md`，并给出每表每列的判定（UTC / 本地 / 混杂）。混杂时按行不可判定 → 记录为 `unknown` 并采用保守转换（不猜测偏移，标注数据质量降级）。

### 4.2 转换迁移（验证通过后才执行）

```sql
ALTER TABLE chat_messages ALTER COLUMN timestamp TYPE timestamptz
  USING timestamp AT TIME ZONE 'UTC';   -- 仅当 §4.1 判定为 UTC
```

前置与保障：

| 项 | 要求 |
| --- | --- |
| 备份 | `pg_dump -Fc` 全量 + 校验和；记录 `pg_dump` 的 SHA256 与行数快照 |
| 演练 | 在克隆库上完整跑一遍转换 + 回归计数，产出对照表 |
| 数据校验 | 转换前后各表 `count(*)`、`min/max`、按小时直方图的 KL 差异、抽样 100 行 epoch 一致性 |
| 停机窗口 | 转换期间禁止旧进程写入（旧代码继续写 naive 会污染新列）→ 与 A0-3 的 `create_all` 报错改动同批上线 |
| 恢复 | `pg_restore` 到临时库比对；回滚脚本 = 反向 `ALTER ... TYPE timestamp USING col AT TIME ZONE 'UTC'`，**且只在未写入新数据时有效** |
| 新表 | `paper_*`、`research_*` 一律 `timestamptz`，从第一天起不继承旧问题 |

**默认值统一**：Python 侧全面改用 `datetime.now(timezone.utc)`，禁止 `utcnow()`（已 deprecated，见 00-audit §1 告警）。

## 5. 存量文献重解析与索引重建

**硬约束**：不得把 Milvus 中已截断的 `text` 当完整原文（决策 Q5）。重建只能从原始 PDF 出发。

`scripts/rebuild_chunks.py`（A0-4）：

```
--dry-run | --paper <display_name> | --limit N | --reindex | --verify-only
```

1. **原料可用性检查**：原始 PDF 位于 `backend/data/documents/`（`paths.py:8`）。枚举现有 Milvus `filename` 集合，与磁盘文件、`ingested.json` 记录三方对账 → 输出 `missing_source` 清单，这些文献**必须重新上传**，脚本明确标记为不可自动重建，不静默跳过。
2. **逐文献重解析**：走现有 `DocumentLoader.load_document()`（修复后的分层版本，见 06 A0-4），产出 level 1/2/3 全量 chunk。
3. **写 PG**：建/复用 `papers` → `paper_versions(version_no+1, raw_sha256)` → `paper_files(object_id)` → `paper_sections` → `paper_chunks`（`ON CONFLICT` upsert）。
4. **建索引**：调 `MilvusWriter`（复用 `rag/embedding.py` 的 dense + 手写 BM25），同事务写 `paper_chunk_vectors(index_state)`。
5. **一致性校验**：每个版本比对 `count(paper_chunks where level=3)` vs `count(paper_chunk_vectors where index_state='ready')`；不等则 `index_state='stale'` 并**保留可检索降级**（PG 可用，向量缺失只降级不报错）。
6. **公式索引**：入库后调用 `_build_formula_index`（当前无人调用，见 03 §3 D1），索引落 PG 表 `formula_index_entries(formula_norm, chunk_id)`，不再只靠进程内 LSH 单例（重启即空是 D1 的第二重病因）。
7. **切换**：新版本 `index_state='ready'` 后，把 `papers.current_version_id` 指向它；旧版本 chunk 保留，`Milvus` 删除在确认切换成功后异步执行（避免"先删后建"造成检索空窗）。

**验收**：任取一篇，`SELECT chunk_id, page_number, start_char, length(text) FROM paper_chunks WHERE paper_version_id=? AND level=3` 的正文总长 ≥ 解析器输出的 normalized full text 长度的 95%（无截断证据）；随机 20 个 chunk 能按 `page_number`+`start_char` 在 PDF 上人工复核到原文。
