from backend.rag.formula_index import FormulaLSHIndex, reset_formula_lsh_index


class TestFormulaLSHIndex:
    def setup_method(self):
        self.index = FormulaLSHIndex()

    def test_add_and_query_similar(self):
        self.index.add("E=mc^2", "f1")
        self.index.add("E = m c^2", "f2")
        self.index.add("completely_different", "f3")

        results = self.index.query("E = mc^2", top_k=5)
        ids = {r[0] for r in results}
        assert "f1" in ids
        assert "f2" in ids

    def test_query_top_k_limit(self):
        for i in range(5):
            self.index.add(f"formula_{i}", f"f{i}")

        results = self.index.query("formula_0", top_k=3)
        assert len(results) <= 3

    def test_remove(self):
        self.index.add("test", "f1")
        self.index.add("test", "f2")
        assert len(self.index) == 2

        self.index.remove("f1")
        assert len(self.index) == 1

        results = self.index.query("test")
        assert "f1" not in {r[0] for r in results}

    def test_clear(self):
        self.index.add("formula_alpha", "f1")
        self.index.add("formula_beta", "f2")
        assert len(self.index) == 2

        self.index.clear()
        assert len(self.index) == 0

    def test_add_from_list(self):
        pairs = [("alpha", "f1"), ("beta", "f2"), ("gamma", "f3")]
        self.index.add_from_list(pairs)
        assert len(self.index) == 3

    def test_empty_query(self):
        assert self.index.query("") == []
        assert self.index.query("x") == []
        assert len(self.index) == 0

    def test_add_empty_formula(self):
        self.index.add("", "empty")
        self.index.add("   ", "whitespace")
        assert len(self.index) == 0


class TestGlobalSingleton:
    def teardown_method(self):
        reset_formula_lsh_index()

    def test_get_global_index(self):
        from backend.rag.formula_index import get_formula_lsh_index

        idx = get_formula_lsh_index()
        assert idx is not None
        assert len(idx) == 0

    def test_reset(self):
        from backend.rag.formula_index import get_formula_lsh_index

        idx = get_formula_lsh_index()
        idx.add("test", "f1")
        assert len(idx) == 1

        reset_formula_lsh_index()
        idx2 = get_formula_lsh_index()
        assert idx2 is not idx
        assert len(idx2) == 0
