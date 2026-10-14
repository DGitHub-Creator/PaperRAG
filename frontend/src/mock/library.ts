// 书架 / 阅读器的示例数据（`docs/rules/10-frontend-structure.md` §7.1）。
// ⚠️ 本目录是纯前端占位：内容全用英文（学术数据本就是英文），既过 R9，也不会被误认成真实接口数据。
// 升级为真实：M1/M2/M9 的卡片（P1-3 / P2-9 / P2-10）转 done 时，把这里的读取换成 composable + api/client 调用。

export interface MockTopic {
  id: string
  name: string
  count: number
  keywords: string[]
}

export interface MockPaper {
  id: string
  title: string
  authors: string
  venue: string
  year: number
  citations: number
  topic: string
  tags: string[]
  status: string
}

export interface MockCrawlSource {
  id: string
  kind: string
  query: string
  cadence: string
  lastRun: string
  newItems: number
}

export const TOPICS: MockTopic[] = [
  { id: "t1", name: "Retrieval-Augmented Generation", count: 42, keywords: ["retrieval", "grounding", "faithfulness"] },
  { id: "t2", name: "Long-Context Transformers", count: 28, keywords: ["attention", "sparsity", "context window"] },
  { id: "t3", name: "Scientific Document Understanding", count: 19, keywords: ["layout", "math OCR", "tables"] },
  { id: "t4", name: "Agentic Tool Use", count: 23, keywords: ["planning", "tools", "verification"] },
  { id: "t5", name: "Evaluation & Benchmarks", count: 15, keywords: ["benchmark", "rubric", "human eval"] },
]

export const PAPERS: MockPaper[] = [
  {
    id: "p1",
    title: "Grounded Retrieval with Verifier-in-the-Loop Citations",
    authors: "A. Novak, M. Lee, R. Sharma",
    venue: "ACL",
    year: 2025,
    citations: 214,
    topic: "t1",
    tags: ["RAG", "citation", "verification"],
    status: "parsed",
  },
  {
    id: "p2",
    title: "Sparse Attention Revisited: Budgeted Context for Long Papers",
    authors: "L. Chen, P. Okafor",
    venue: "NeurIPS",
    year: 2025,
    citations: 158,
    topic: "t2",
    tags: ["attention", "efficiency"],
    status: "parsed",
  },
  {
    id: "p3",
    title: "Layout-Aware Parsing of Scientific Figures and Tables",
    authors: "S. Ito, D. Rivas",
    venue: "EMNLP",
    year: 2024,
    citations: 96,
    topic: "t3",
    tags: ["layout", "tables", "parsing"],
    status: "parsed",
  },
  {
    id: "p4",
    title: "Plan, Retrieve, Verify: An Agent Loop for Literature Review",
    authors: "K. Mensah, T. Berg",
    venue: "ICLR",
    year: 2026,
    citations: 41,
    topic: "t4",
    tags: ["agent", "planning", "review"],
    status: "queued",
  },
  {
    id: "p5",
    title: "Faithfulness Metrics Do Not Transfer Across Domains",
    authors: "Y. Petrova, H. Nakamura",
    venue: "TACL",
    year: 2025,
    citations: 133,
    topic: "t5",
    tags: ["evaluation", "faithfulness"],
    status: "parsed",
  },
  {
    id: "p6",
    title: "Chunking Strategies and Their Hidden Effect on Recall",
    authors: "J. Alvarez, N. Rahman",
    venue: "SIGIR",
    year: 2025,
    citations: 77,
    topic: "t1",
    tags: ["chunking", "recall"],
    status: "failed",
  },
]

export const CRAWL_SOURCES: MockCrawlSource[] = [
  { id: "c1", kind: "arXiv", query: "cat:cs.CL AND abs:retrieval augmented", cadence: "daily", lastRun: "2026-10-13 06:00", newItems: 7 },
  { id: "c2", kind: "arXiv", query: "cat:cs.LG AND abs:long context", cadence: "daily", lastRun: "2026-10-13 06:00", newItems: 3 },
  { id: "c3", kind: "Semantic Scholar", query: "cited-by: Grounded Retrieval (p1)", cadence: "weekly", lastRun: "2026-10-11 06:00", newItems: 12 },
  { id: "c4", kind: "DOI watch", query: "10.48550/* + venue:ACL/EMNLP", cadence: "weekly", lastRun: "2026-10-11 06:00", newItems: 0 },
]

export interface MockReaderChunk {
  id: string
  page: number
  heading: string
  text: string
  cited: boolean
}

export const READER_SECTIONS: MockReaderChunk[] = [
  {
    id: "r1",
    page: 3,
    heading: "3.1 Retriever",
    text: "We use a bi-encoder retriever over passage-level chunks and keep the top-k candidates before reranking.",
    cited: true,
  },
  {
    id: "r2",
    page: 4,
    heading: "3.2 Verifier",
    text: "Each generated sentence is aligned to at most one supporting passage; unsupported sentences are flagged rather than dropped.",
    cited: true,
  },
  {
    id: "r3",
    page: 6,
    heading: "4.2 Ablations",
    text: "Removing the verifier reduces citation precision by 11.3 points while leaving answer fluency unchanged.",
    cited: false,
  },
]
