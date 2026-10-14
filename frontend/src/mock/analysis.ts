// 分析类页面的示例数据：比较矩阵 / Gap Explorer / 知识双图（`docs/rules/10-frontend-structure.md` §7.1）。
// ⚠️ 纯前端占位，内容全英文；升级判据见同目录 library.ts 顶部说明。

export interface MockMatrixColumn {
  id: string
  label: string
  venue: string
  year: number
}

export interface MockMatrixRow {
  dimension: string
  /** 与 MATRIX_COLUMNS 同序：每篇论文在该维度上的取值 */
  values: string[]
}

export const MATRIX_COLUMNS: MockMatrixColumn[] = [
  { id: "p1", label: "Verifier-in-the-loop", venue: "ACL", year: 2025 },
  { id: "p4", label: "Plan-Retrieve-Verify", venue: "ICLR", year: 2026 },
  { id: "p5", label: "Faithfulness Transfer", venue: "TACL", year: 2025 },
  { id: "p6", label: "Chunking & Recall", venue: "SIGIR", year: 2025 },
]

export const MATRIX_ROWS: MockMatrixRow[] = [
  { dimension: "Corpus size", values: ["120k passages", "1.2M abstracts", "3 domains", "40k papers"] },
  { dimension: "Retriever", values: ["bi-encoder + rerank", "tool-use search", "n/a (analysis)", "BM25 + dense"] },
  { dimension: "Citation check", values: ["per-sentence verifier", "post-hoc audit", "metric only", "none"] },
  { dimension: "Chunking", values: ["passage-level", "section-level", "n/a", "4 strategies"] },
  { dimension: "Reported metric", values: ["citation precision", "task success", "faithfulness F1", "recall@10"] },
  { dimension: "Human eval", values: ["2 annotators", "none", "5 annotators", "none"] },
]

export interface MockGap {
  id: string
  title: string
  evidenceCount: number
  support: number
  status: "candidate" | "backed" | "rejected"
  note: string
}

export const GAPS: MockGap[] = [
  {
    id: "g1",
    title: "Verifier quality is never measured against retrieval recall",
    evidenceCount: 7,
    support: 0.82,
    status: "backed",
    note: "Three papers report precision gains; none report the recall floor.",
  },
  {
    id: "g2",
    title: "Chunk boundaries are treated as a hyperparameter, not a modeling choice",
    evidenceCount: 4,
    support: 0.61,
    status: "candidate",
    note: "Contradicting result in p6 on long technical sections.",
  },
  {
    id: "g3",
    title: "Long-context models make retrieval unnecessary",
    evidenceCount: 2,
    support: 0.24,
    status: "rejected",
    note: "Cost analysis in p2 caps usable context well below paper length.",
  },
]

export interface MockHypothesis {
  id: string
  statement: string
  frontier: "explore" | "test" | "refine" | "parked"
  cost: string
}

export const HYPOTHESES: MockHypothesis[] = [
  { id: "h1", statement: "Recall floor bounds verifier precision, not the reverse.", frontier: "test", cost: "6 h" },
  { id: "h2", statement: "Section-aware chunking raises recall on methods sections.", frontier: "explore", cost: "4 h" },
  { id: "h3", statement: "Citation precision saturates once top-k exceeds 12.", frontier: "refine", cost: "3 h" },
  { id: "h4", statement: "Sparse attention removes the need for a reranker.", frontier: "parked", cost: "10 h" },
]

export interface MockGraphNode {
  id: string
  label: string
  kind: "claim" | "evidence" | "paper" | "method"
  x: number
  y: number
}

export interface MockGraphEdge {
  from: string
  to: string
  relation: string
}

export const GRAPH_NODES: MockGraphNode[] = [
  { id: "n1", label: "Verifier raises citation precision", kind: "claim", x: 380, y: 60 },
  { id: "n2", label: "p1 §3.2 ablation", kind: "evidence", x: 180, y: 150 },
  { id: "n3", label: "Grounded Retrieval (p1)", kind: "paper", x: 60, y: 250 },
  { id: "n4", label: "aligned-to-passage check", kind: "method", x: 300, y: 250 },
  { id: "n5", label: "Recall floor is unreported", kind: "claim", x: 600, y: 150 },
  { id: "n6", label: "p5 §5 cross-domain", kind: "evidence", x: 560, y: 300 },
  { id: "n7", label: "Faithfulness Transfer (p5)", kind: "paper", x: 700, y: 250 },
]

export const GRAPH_EDGES: MockGraphEdge[] = [
  { from: "n2", to: "n1", relation: "supports" },
  { from: "n3", to: "n2", relation: "reports" },
  { from: "n4", to: "n1", relation: "implements" },
  { from: "n3", to: "n4", relation: "introduces" },
  { from: "n6", to: "n5", relation: "supports" },
  { from: "n7", to: "n6", relation: "reports" },
  { from: "n1", to: "n5", relation: "tension" },
]
