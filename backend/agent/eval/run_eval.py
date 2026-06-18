"""Evaluation system for the Agent."""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def load_dataset(split: str = "full_corpus") -> List[dict]:
    """加载评估数据集"""
    data_path = Path(__file__).parent / "data" / "qa_cases.jsonl"
    cases = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            case = json.loads(line.strip())
            if case.get("split") == split:
                cases.append(case)
    return cases


def evaluate_answer(answer: str, criteria: str, expected_sources: List[str]) -> dict:
    """评估答案质量"""
    has_citations = bool(re.search(r'\[.*?\.pdf\s*\(p\.\d+\)\]', answer))
    sources_matched = all(
        any(src in answer for src in [s])
        for s in expected_sources
    )
    
    return {
        "has_citations": has_citations,
        "sources_matched": sources_matched,
        "criteria_met": True,
    }


def run_eval(split: str = "full_corpus", categories: List[str] = None):
    """运行评估"""
    from backend.agent.core import build_agent
    
    agent = build_agent()
    cases = load_dataset(split)
    
    if categories:
        cases = [c for c in cases if c.get("category") in categories]
    
    results = []
    for case in cases:
        try:
            output = agent.invoke({
                "question_input": {"question": case["question"]},
                "messages": [],
                "classification_decision": None,
                "trace": [],
                "retrieved_locators": [],
                "evidence": [],
            })
            
            evaluation = evaluate_answer(
                str(output.get("answer", "")),
                case.get("criteria", ""),
                case.get("expected_sources", [])
            )
            
            results.append({
                "question": case["question"],
                "category": case.get("category"),
                "evaluation": evaluation,
            })
        except Exception as e:
            logger.error("Evaluation failed for: %s", case["question"])
            results.append({"question": case["question"], "error": str(e)})
    
    total = len(results)
    correct = sum(1 for r in results if r.get("evaluation", {}).get("sources_matched"))
    
    print(f"\n=== Evaluation Results ===")
    print(f"Total: {total}")
    print(f"Correct: {correct}")
    if total > 0:
        print(f"Accuracy: {correct/total*100:.1f}%")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run evaluation")
    parser.add_argument("--split", default="full_corpus", help="Dataset split")
    parser.add_argument("--categories", nargs="+", help="Filter by categories")
    args = parser.parse_args()
    
    run_eval(split=args.split, categories=args.categories)