"""LLM 调用预算追踪单元测试。"""

from unittest.mock import patch


class TestBudgetTracker:
    def test_reset_budget(self):
        from backend.core.budget import reset_budget, _call_count_var, _estimated_tokens_var
        _call_count_var.set(10)
        _estimated_tokens_var.set(5000)
        reset_budget()
        assert _call_count_var.get() == 0
        assert _estimated_tokens_var.get() == 0

    def test_record_llm_call(self):
        from backend.core.budget import reset_budget, record_llm_call, _call_count_var, _estimated_tokens_var
        reset_budget()
        record_llm_call(estimated_tokens=200)
        record_llm_call(estimated_tokens=300)
        assert _call_count_var.get() == 2
        assert _estimated_tokens_var.get() == 500

    def test_budget_ok_within_limit(self):
        from backend.core.budget import reset_budget, record_llm_call, budget_ok
        reset_budget()
        record_llm_call(estimated_tokens=100)
        assert budget_ok() is True

    def test_budget_exceeds_call_limit(self):
        from backend.core.budget import reset_budget, record_llm_call, budget_ok
        reset_budget()
        for _ in range(6):
            record_llm_call(estimated_tokens=10)
        assert budget_ok() is False

    def test_budget_exceeds_cost_limit(self):
        from backend.core.budget import reset_budget, record_llm_call, budget_ok
        reset_budget()
        # 6000 tokens * $0.01/1k = $0.06 > $0.05 limit
        record_llm_call(estimated_tokens=6000)
        assert budget_ok() is False

    def test_get_budget_status(self):
        from backend.core.budget import reset_budget, record_llm_call, get_budget_status
        reset_budget()
        record_llm_call(estimated_tokens=500)
        status = get_budget_status()
        assert status["call_count"] == 1
        assert status["estimated_tokens"] == 500
        assert status["max_calls"] == 6
