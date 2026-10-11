# 05 — PostgreSQL Schema 收编与 Chunk 数据重建

> **本文状态（2026-10-09 复核）**：性质=**实施**（Schema 收编七步、`paper_chunks` DDL、TIMESTAMPTZ 验证与转换、存量重建）。里程碑口径一律用 **P0–P3**；旧 `Milestone A/B/C`、`A0-x` 的对应关系见 [04 §0/§3](04-migration.md)。**除核查脚本外全部未实现**：`scripts/audit_schema.py` 已落（P0-2，离线 `--check-baseline` + 只读 `--live`，19 项判定单测）；基线迁移、`paper_chunks`、时间戳转换、`rebuild_chunks.py` 都要真实 PG，本机无 Docker → `not_run`。**基线 DDL 必须由实际库结构抄录，禁止由 ORM 生成**（§1 末）。
> 对应决策 Q4、Q5。原则：**先核查、后建基线、禁止对存量库重复初始化建表**；Milvus 降级为可重建索引，PostgreSQL 成为文献与分块正文的唯一真相（02 §0 L3）。

## 1. 收编前置核查（必须在任何写操作之前完成）

存量库不可信任：`init_db()` 在 alembic 失败时静默回退 `Base.metadata.create_all`（`core/database.py:99-120`），所以**库可能物理存在表但没有任何 `alembic_version` 行**。真库已核查（`schema-baseline.json`，2026-10-11）：**10 张表，含 `alembic_version`**；`alembic_version` 是否算 Go 基线对象**待决策**（P0-2 的 `000001_baseline` 目前含它）。

核查脚本 `scripts/audit_schema.py`（**P0-2** 交付，只读）：

| 检查 | 方法 | 判定 |
| --- | --- | --- |
| 实际表集合 | `information_schema.tables WHERE table_schema='public'` | 与 `models.py` 声明的 9 表 diff；**真库实测 10 张表**（多出的 `alembic_version` 是迁移历史表，非业务表） |
| 迁移版本 | `SELECT version_num FROM alembic_version`（表不存在 = 曾走 create_all） | 三种情形：无表 / 空 / head 不符 |
| 列级漂移 | `information_schema.columns` vs SQLAlchemy `Base.metadata`（类型、可空、server_default） | 逐字段 diff 报告 |
| 索引与约束 | `pg_indexes` + `pg_constraint` | 已知漂移：`ix_paper_nodes_id` 缺失；`filename` 是唯一索引而非 UNIQUE 约束（sqlc 经 `constraint_type='u'` 查不到） |
| 数据体量 | 每表 `count(*)`、时间列 `min/max` | 决定迁移是否可在线执行 |
| 时区真相 | 见 §4 | 决定 TIMESTAMPTZ 转换方式 |

**产出**：`docs/refactor/schema-baseline.json`（结构快照，进仓库）。Go 的迁移基线由此生成，**不由 ORM 直接生成**。

## 2. 冻结 alembic，建立 golang-migrate 基线

> **迁移文件形态**：`server/migrations/*.sql` 是纯 SQL + `migrate` 约定的 `.down.sql`，**不需要任何 Go 代码即可执行**（用 `migrate/migrate` 镜像或 CLI：`docker run --rm migrate/migrate -path /migrations -database "$DATABASE_URL" up`）。因此 **P0-2** 可以在 Go 服务还不存在时就按同一套迁移文件建表，而不必回头再引入第二套迁移工具。

| 步骤 | 动作 | 约束 |
| --- | --- | --- |
| 2.1 | 停用 `init_db()` 的 alembic 调用与 `create_all` 兜底 | 改为：探测 schema 与基线不符 → **记录差异并抛出启动失败**（禁止任何隐式建表）。对应决策 Q4「删除静默兜底，改为明确报错」 |
| 2.2 | 生成 `server/migrations/000001_baseline.{up,down}.sql` | 内容 = §1 核查出的**实际结构**（不是 ORM 声明），含**真库 10 张表**（9 张业务表 + `alembic_version`）+ 索引 + 约束 |
| 2.3 | 存量库打基线戳 | `migrate version 1`（只写 `schema_migrations`，不执行 DDL）；新库走 `000001_baseline.up.sql` |
| 2.4 | `alembic/` 保留为只读历史 | 在 `alembic/README` 与 CI 中标注 FROZEN；禁止新增 revision。`models.py` 继续用于 Python 侧 ORM 读，但**不再作为 schema 来源** |
| 2.5 | 漂移修复作为第一个后续迁移 | `000002_fix_drift`：补 `ix_paper_nodes_id`；`paper_nodes.filename` 唯一索引转 UNIQUE 约束（**先核查是否与现网语义等价**，等价则记为"不改"，避免无收益 DDL） |

**幂等纪律**：所有迁移可重复执行安全检查；`down` 必须真实可回退，禁止 `down` 里写 `DROP TABLE IF EXISTS` 掩盖问题。

## 3. Chunk 可信化：新表设计

现状问题（03 §2）：叶子块正文只在 Milvus 且 `VARCHAR(2000)` 截断；`parent_chunks` 只收 level 1/2 而 PDF 默认路径不产 → 实际近空；无版本、无定位、无哈希。

新增（`server/migrations/000003_paper_chunks.sql`，**P2-1** 交付；DDL 由 Go 侧迁移文件持有，Python 同期加 SQLAlchemy 映射读取）：

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

`ParentChunkStore`（`rag/parent_chunk_store.py`）改为读写 `paper_chunks`（`level IN (1,2)`），Redis Cache-Aside 逻辑不变；`parent_chunks` 表在 **P1** 的阶段 3（[04 §4.1](04-migration.md) 的切换阶段）之后 DROP（届时它仍近乎空，无数据搬迁成本）。**A0 不删表**，保证 Python 检索路径随时可回退。

## 4. TIMESTAMPTZ 统一（决策 Q4：先验证再转换）

现状：所有列为 `timestamp without time zone`；写入混用 naive `datetime.utcnow()`（`conversation_storage.py:85`、`models.py` 各默认值）与 aware `datetime.now(UTC)`（`parent_chunk_store.py:95`）。aware 值经 psycopg2 落到 `timestamp` 列时，**PG 会按会话 `TimeZone` 转换后再丢弃偏移** → 存量数值的真实语义取决于历史会话时区与 `log_timezone`，**不能假定为 UTC**。

### 4.1 验证（只读，**P0-2**）

```sql
SHOW timezone;  SHOW log_timezone;  -- 以及 server_version
```

1. **探针法**：写入一行已知 UTC 时刻（`INSERT ... VALUES (now() AT TIME ZONE 'UTC')` 与 `datetime.now(UTC)` 两条路径各一），用 `SELECT col, extract(epoch from col)` 读回，比较与真实 epoch 的偏移 → 得到"写入路径 × 会话时区 → 落库语义"的映射。
2. **分布法**：对 `users.created_at`、`chat_messages.timestamp` 做小时直方图。若峰值集中在 UTC 工作时段之外 8 小时（+08:00 特征），说明落库值是本地时间；与运维记录/已知事件时刻交叉验证。
3. **交叉法**：同一会话内 `chat_messages.timestamp` 与该行 `id` 递增顺序（serial 单调）应单调不减；违例数量指示混用规模。

**结论写入** `docs/refactor/timestamp-audit.md`，并给出每表每列的判定（UTC / 本地 / 混杂）。混杂时按行不可判定 → 记录为 `unknown` 并采用保守转换（不猜测偏移，标注数据质量降级）。

### 4.2.1 已核查的列级事实与更正（2026-10-11，依据 `schema-baseline.json`）

本文**没有**出现过「`users.created_at` / `users.role` 在库里没有 DEFAULT」这类断言，所以这里不是改错句，而是把**真库核查的结论**登记下来，防止它被 `server/sql/schema.sql` 的注释带回文档：

- `users.created_at` 真库有 **`DEFAULT now()`**；`users.role` 真库有 **`DEFAULT 'user'`**。
- **依据**：这两列**没有**出现在 `schema-baseline.json` 的 `column_diff`（23 条）里。`scripts/audit_schema.py:233` 的判定是 `if a[col].get("column_default") is None` → 纯按**真库** `information_schema.columns.column_default` 是否为空投 diff，与 ORM 是否声明 `server_default` 无关，所以"没出现"等价于"库里有默认值"。
- **旁证**：出现该差异的 23 列全是应用必填列（`username`/`password_hash`/`filename`/`chunk_id`/`text`/`definition`/外键 …）。所以"有默认值"这件事只能来自库**自己的** DDL，不可能是 ORM 客户端默认值被误认。
- **⚠️ 已知失真**：`server/sql/schema.sql`（P0-3 的临时参照）在同样两列上是错的——该文件第 22、25 行的注释写「DDL 里没有 DEFAULT / 库里无 DEFAULT」。真实库有。这是 **P0-3 的已知差异**：`sqlc.yaml` 的 schema 从 `schema.sql` 切到 `migrations/` 时必须把这两列当已知差异逐条核对（`column_diff` 覆盖的是列级**默认值/类型/存在性**，校验器并**不检查** varchar 长度与 NOT NULL，所以长度与可空性**目前无机检覆盖**）。
- **对 Go 的后果**：`role`/`created_at` 可省略让 PG 补默认值（不再必然撞 NOT NULL violation）；切到 `timestamptz` 后 `DEFAULT now()` 是 **aware** 默认值，含义明确，正好落在本节的转换方向上。

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
| 停机窗口 | 转换期间禁止旧进程写入（旧代码继续写 naive 会污染新列）→ 与已完成的 A0-3（`d8f1563`，删静默 `create_all`）同批上线 |
| 恢复 | `pg_restore` 到临时库比对；回滚脚本 = 反向 `ALTER ... TYPE timestamp USING col AT TIME ZONE 'UTC'`，**且只在未写入新数据时有效** |
| 新表 | `paper_*`、`research_*` 一律 `timestamptz`，从第一天起不继承旧问题 |

**默认值统一**：Python 侧全面改用 `datetime.now(timezone.utc)`，禁止 `utcnow()`（已 deprecated，见 00-audit §1 告警）。

## 5. 存量文献重解析与索引重建

**硬约束**：不得把 Milvus 中已截断的 `text` 当完整原文（决策 Q5）。重建只能从原始 PDF 出发。

`scripts/rebuild_chunks.py`（**P2-1**）：

```
--dry-run | --paper <display_name> | --limit N | --reindex | --verify-only
```

1. **原料可用性检查**：原始 PDF 位于 `backend/data/documents/`（`paths.py:8`）。枚举现有 Milvus `filename` 集合，与磁盘文件、`ingested.json` 记录三方对账 → 输出 `missing_source` 清单，这些文献**必须重新上传**，脚本明确标记为不可自动重建，不静默跳过。
2. **逐文献重解析**：走现有 `DocumentLoader.load_document()`（修复后的分层版本，见 [../archive/refactor-06-milestone-a0.md](../archive/refactor-06-milestone-a0.md) 的 A0-4（已归档）），产出 level 1/2/3 全量 chunk。
3. **写 PG**：建/复用 `papers` → `paper_versions(version_no+1, raw_sha256)` → `paper_files(object_id)` → `paper_sections` → `paper_chunks`（`ON CONFLICT` upsert）。
4. **建索引**：调 `MilvusWriter`（复用 `rag/embedding.py` 的 dense + 手写 BM25），同事务写 `paper_chunk_vectors(index_state)`。
5. **一致性校验**：每个版本比对 `count(paper_chunks where level=3)` vs `count(paper_chunk_vectors where index_state='ready')`；不等则 `index_state='stale'` 并**保留可检索降级**（PG 可用，向量缺失只降级不报错）。
6. **公式索引**：入库后调用 `_build_formula_index`（当前无人调用，见 03 §3 D1），索引落 PG 表 `formula_index_entries(formula_norm, chunk_id)`，不再只靠进程内 LSH 单例（重启即空是 D1 的第二重病因）。
7. **切换**：新版本 `index_state='ready'` 后，把 `papers.current_version_id` 指向它；旧版本 chunk 保留，`Milvus` 删除在确认切换成功后异步执行（避免"先删后建"造成检索空窗）。

**验收**：任取一篇，`SELECT chunk_id, page_number, start_char, length(text) FROM paper_chunks WHERE paper_version_id=? AND level=3` 的正文总长 ≥ 解析器输出的 normalized full text 长度的 95%（无截断证据）；随机 20 个 chunk 能按 `page_number`+`start_char` 在 PDF 上人工复核到原文。

## 6. 与产品愿景的关系

> 对照 [11-product-vision.md](11-product-vision.md)（产品轴 V1–V4）。本文只管数据面，产品级缺口集中记在 `11 §8`，此处不复述。

**已覆盖**：`11 §4.2 Deep Reader` 的数据前提（`paper_chunks` 持完整正文 + `page_number`/`start_char` 定位 + `chapter_path`，是"每次回答可跳转 PDF 位置"的地基）· `11 §4.1 AI 论文图书馆` 的实体层（`papers`/`paper_versions`/`paper_files`，`raw_sha256` 去重与版本寻址，即"为什么这篇在我的库里"的落点）· `11 §4.7 Research Lab` 的公式前提（`formula_index_entries`，即 V1.0 的"公式/定理检索"）。

**未覆盖**：`11 §4.3 Multi-Paper 比较矩阵 / Paper Diff`（`paper_versions` 只提供版本寻址，不做方法/假设/定理差异比对）· `11 §4.5 Research Knowledge Graph` 与 `§4.6 Gap Explorer / Hypothesis Board`（无假设、缺口、探索图表）· `11 §4.2` 的**定理/证明级解析**（DDL 只有 `has_theorem`/`has_proof` 布尔标记，没有定理前提/结论/证明步骤/依赖引理的结构）· `11 §4.8 Research Writing` 与 `§4.9 Research Radar`（无报告版本表、无文献变化追踪）· `11 §4.10 Research Workspace`（无项目/任务/笔记/报告/预算表）。全部指向 `11 §8`。

**需拍板/冲突**：无与本文冲突的口径。唯一待决策："`alembic_version` 算不算 Go 基线对象"（P0-2 的基线迁移目前含它，见 §1/§2.2）——选项 A：含它（新库迁移链与 Go 迁移工具共存，需明确谁写版本行）；选项 B：排除它，把它当 Python 侧历史遗留、由 `migrate` 的 `schema_migrations` 独占版本真相。
