"""Run a small RAG regression suite against the local knowledge base."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.rag.rag_pipeline import run_rag_graph


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_case(case: dict) -> dict:
    result = run_rag_graph(case["question"])
    docs = result.get("docs", []) if isinstance(result, dict) else []
    context = result.get("context", "") if isinstance(result, dict) else ""
    expected_terms = [term.lower() for term in case.get("expected_terms", [])]
    context_lower = context.lower()
    matched_terms = [term for term in expected_terms if term in context_lower]
    min_sources = int(case.get("min_sources", 1))
    passed = len(docs) >= min_sources and len(matched_terms) == len(expected_terms)
    return {
        "id": case["id"],
        "passed": passed,
        "doc_count": len(docs),
        "matched_terms": matched_terms,
        "missing_terms": [term for term in expected_terms if term not in matched_terms],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/fixtures/rag_regression_cases.json"),
    )
    args = parser.parse_args()

    results = [evaluate_case(case) for case in load_cases(args.cases)]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
