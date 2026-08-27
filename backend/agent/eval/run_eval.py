"""Evaluation system for the Agent.

黄金评测集见 ``data/qa_cases.jsonl``。每行一个 JSON 用例，字段：

  - id:               用例唯一标识
  - split:            数据集划分（默认 full_corpus）
  - category:         问题类型（definition/formula/proof/comparison/citation/method/refusal）
  - question:         用户问题
  - expected_terms:   答案中必须出现的关键词（可为空 = 跳过该项检查）
  - expected_sources: 期望引用的文件名列表（可为空 = 跳过该项检查）
  - min_citations:    答案中至少需要的已验证引用数（0 = 不检查）
  - expect_refusal:   期望拒答（out-of-scope 问题，答案不应包含编造引用）

评测走完整 Agent 链路（含意图路由、检索、引用校验），可真实反映线上行为。
运行前提：后端基础设施（PostgreSQL/Milvus/Redis）与 LLM 配置可用。

用法：
    python -m backend.agent.eval.run_eval [--split full_corpus]
                                         [--categories definition formula]
                                         [--user-id eval_user]
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_REFUSAL_PATTERNS = (
    "超出知识库范围",
    "无法回答",
    "out of scope",
    "cannot answer",
    "not covered",
    "don't have enough information",
    "no relevant documents",
)


def load_dataset(split: str = "full_corpus") -> list[dict]:
    """加载评估数据集。

    缺少 split 字段的行视为属于所有划分。
    """
    data_path = Path(__file__).parent / "data" / "qa_cases.jsonl"
    cases = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case_split = case.get("split", split)
            if case_split == split:
                cases.append(case)
    return cases


def evaluate_answer(
    answer: str,
    case: dict,
    citations: list | None = None,
    unsupported: list | None = None,
    source_map: dict | None = None,
) -> dict:
    """评估答案质量。

    判定维度：
      - citations_present: 已验证引用数达到 min_citations
      - sources_matched:   期望文件均出现在 source_map 中
      - criteria_met:      expected_terms 全部出现在答案里
      - refused_correctly: expect_refusal 的用例确实拒答（且无编造引用）
    """
    citations = citations or []
    unsupported = unsupported or []
    answer = answer or ""

    min_citations = int(case.get("min_citations", 1))
    citations_present = len(citations) >= min_citations

    expected_sources = case.get("expected_sources") or []
    retrieved_files = {
        str(loc.get("filename") or "") for loc in (source_map or {}).values()
    }
    sources_matched = all(
        any(expected in f or f in expected for f in retrieved_files if f)
        for expected in expected_sources
    ) if expected_sources else True

    expected_terms = [t.lower() for t in case.get("expected_terms") or []]
    answer_lower = answer.lower()
    matched_terms = [t for t in expected_terms if t in answer_lower]
    criteria_met = len(matched_terms) == len(expected_terms)

    expect_refusal = bool(case.get("expect_refusal", False))
    if expect_refusal:
        refused = any(p in answer_lower for p in _REFUSAL_PATTERNS)
        refused_correctly = refused and not citations
    else:
        refused_correctly = True

    passed = citations_present and sources_matched and criteria_met and refused_correctly

    return {
        "citations_present": citations_present,
        "verified_citations": len(citations),
        "unsupported_citations": len(unsupported),
        "sources_matched": sources_matched,
        "criteria_met": criteria_met,
        "matched_terms": matched_terms,
        "missing_terms": [t for t in expected_terms if t not in matched_terms],
        "refused_correctly": refused_correctly,
        "passed": passed,
    }


def run_eval(
    split: str = "full_corpus",
    categories: list[str] | None = None,
    user_id: str = "eval_user",
) -> list[dict]:
    """运行评估：走完整 Agent 链路。"""
    from backend.agent.core import run_agent

    cases = load_dataset(split)
    if categories:
        cases = [c for c in cases if c.get("category") in categories]

    results = []
    for case in cases:
        try:
            outcome = run_agent(
                case["question"],
                user_id=user_id,
                session_id=f"eval-{case['id']}",
            )
            evaluation = evaluate_answer(
                outcome.get("response", ""),
                case,
                citations=outcome.get("citations", []),
                unsupported=outcome.get("unsupported", []),
                source_map=outcome.get("source_map"),
            )
            results.append({
                "id": case["id"],
                "category": case.get("category"),
                "evaluation": evaluation,
            })
        except Exception as e:
            logger.exception("Evaluation failed for: %s", case["id"])
            results.append({"id": case["id"], "error": str(e)})

    total = len(results)
    passed = sum(1 for r in results if r.get("evaluation", {}).get("passed"))
    with_errors = sum(1 for r in results if "error" in r)

    print("\n=== Evaluation Results ===")
    print(f"Total: {total}  Passed: {passed}  Errors: {with_errors}")
    if total > 0:
        print(f"Pass rate: {passed / total * 100:.1f}%")
    for r in results:
        status = "PASS" if r.get("evaluation", {}).get("passed") else "FAIL"
        print(f"  [{status}] {r['id']} ({r.get('category', '-')})")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run evaluation")
    parser.add_argument("--split", default="full_corpus", help="Dataset split")
    parser.add_argument("--categories", nargs="+", help="Filter by categories")
    parser.add_argument("--user-id", default="eval_user", help="Eval user id")
    args = parser.parse_args()

    run_eval(split=args.split, categories=args.categories, user_id=args.user_id)
