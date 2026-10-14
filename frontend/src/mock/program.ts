// 运行 / 产出 / 管理类页面的示例数据（`docs/rules/10-frontend-structure.md` §7.1）。
// ⚠️ 纯前端占位，内容全英文；升级判据见同目录 library.ts 顶部说明。

export interface MockRun {
  id: string
  goal: string
  status: "running" | "queued" | "done" | "failed"
  progress: number
  spent: number
  budget: number
  frontier: number
  started: string
}

export const RUNS: MockRun[] = [
  { id: "run-1042", goal: "Map the recall floor across chunking strategies", status: "running", progress: 64, spent: 4.1, budget: 8, frontier: 3, started: "2026-10-13 09:12" },
  { id: "run-1041", goal: "Audit verifier precision on conflicting sentences", status: "done", progress: 100, spent: 6.8, budget: 7, frontier: 2, started: "2026-10-12 14:03" },
  { id: "run-1040", goal: "Compare sparse attention budgets", status: "failed", progress: 38, spent: 2.2, budget: 6, frontier: 5, started: "2026-10-12 08:40" },
  { id: "run-1039", goal: "Draft evidence table for the chunking hypothesis", status: "queued", progress: 0, spent: 0, budget: 3, frontier: 1, started: "-" },
]

export interface MockRunStep {
  id: string
  label: string
  status: "done" | "run" | "pending"
  detail: string
}

export const RUN_STEPS: MockRunStep[] = [
  { id: "s1", label: "Plan", status: "done", detail: "6 sub-questions, 3 accept criteria" },
  { id: "s2", label: "Retrieve", status: "done", detail: "41 passages across 12 papers" },
  { id: "s3", label: "Extract", status: "done", detail: "18 rows, 4 conflicting" },
  { id: "s4", label: "Synthesize", status: "run", detail: "writing section 3 of 5" },
  { id: "s5", label: "Verify", status: "pending", detail: "-" },
  { id: "s6", label: "Report", status: "pending", detail: "-" },
]

export interface MockLabExperiment {
  id: string
  name: string
  tool: string
  status: "draft" | "running" | "verified" | "invalid"
  artifact: string
}

export const LAB_EXPERIMENTS: MockLabExperiment[] = [
  { id: "e1", name: "Recall floor sweep (k = 4..32)", tool: "local python", status: "verified", artifact: "recall_floor.csv" },
  { id: "e2", name: "Verifier precision vs. recall", tool: "local python", status: "running", artifact: "verifier_curve.csv" },
  { id: "e3", name: "Section-aware chunker prototype", tool: "local python", status: "draft", artifact: "-" },
  { id: "e4", name: "Cost model for long-context baseline", tool: "model checker", status: "invalid", artifact: "counterexample.txt" },
]

export interface MockReportSection {
  id: string
  title: string
  status: "done" | "draft" | "empty"
  citations: number
  words: number
}

export const REPORT_SECTIONS: MockReportSection[] = [
  { id: "sec1", title: "1. Scope and questions", status: "done", citations: 6, words: 420 },
  { id: "sec2", title: "2. Retrieval and chunking background", status: "done", citations: 14, words: 880 },
  { id: "sec3", title: "3. Verifier precision vs. recall", status: "draft", citations: 9, words: 610 },
  { id: "sec4", title: "4. Contradictions across papers", status: "draft", citations: 4, words: 300 },
  { id: "sec5", title: "5. Open questions", status: "empty", citations: 0, words: 0 },
]

export interface MockRadarDiff {
  id: string
  paper: string
  kind: "new" | "contradicts" | "extends" | "retracted"
  summary: string
  when: string
}

export const RADAR_DIFFS: MockRadarDiff[] = [
  { id: "d1", paper: "Budgeted Context v2 (arXiv)", kind: "contradicts", summary: "Reports reranker gains under sparse attention, opposite of h4.", when: "2026-10-13" },
  { id: "d2", paper: "Chunking Strategies (SIGIR)", kind: "extends", summary: "Adds two chunkers; recall floor still unreported.", when: "2026-10-12" },
  { id: "d3", paper: "Faithfulness Metrics (TACL)", kind: "new", summary: "New preprint citing p1 with a recall-controlled protocol.", when: "2026-10-11" },
  { id: "d4", paper: "Layout-Aware Parsing (EMNLP)", kind: "retracted", summary: "Author-issued correction on the table extraction numbers.", when: "2026-10-10" },
]

export interface MockProject {
  id: string
  name: string
  role: string
  updated: string
}

export interface MockTask {
  id: string
  title: string
  column: "backlog" | "reading" | "analysis" | "writing" | "done"
  module: string
}

export const PROJECTS: MockProject[] = [
  { id: "pr1", name: "Grounded Retrieval Survey", role: "owner", updated: "2026-10-13" },
  { id: "pr2", name: "Chunking Recall Study", role: "member", updated: "2026-10-11" },
]

export const TASKS: MockTask[] = [
  { id: "t1", title: "Read p2 sparse attention budget", column: "reading", module: "M5" },
  { id: "t2", title: "Extract matrix row: chunking", column: "analysis", module: "M10" },
  { id: "t3", title: "Verify h1 against p5 §5", column: "analysis", module: "M11" },
  { id: "t4", title: "Draft section 4 contradictions", column: "writing", module: "M13" },
  { id: "t5", title: "Set up cost model checker", column: "backlog", module: "M12" },
  { id: "t6", title: "Pin arXiv crawl query", column: "done", module: "M2" },
]

export interface MockBudgetLine {
  label: string
  spent: number
  cap: number
}

export const BUDGET: MockBudgetLine[] = [
  { label: "Retrieval + extraction", spent: 12.4, cap: 20 },
  { label: "Synthesis", spent: 6.1, cap: 12 },
  { label: "Verification", spent: 2.3, cap: 8 },
  { label: "Lab runs", spent: 3.9, cap: 6 },
]
