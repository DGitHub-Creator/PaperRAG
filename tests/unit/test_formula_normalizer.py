from backend.rag.formula_normalizer import (
    extract_formulas,
    formula_similarity,
    normalize_formula,
)


class TestNormalizeFormula:
    def test_strips_whitespace(self):
        result = normalize_formula("  E = mc^2  ")
        assert result == "E=mc^2"

    def test_lowercases_commands(self):
        result = normalize_formula(r"\textbf{X}")
        assert "textbf" in result

    def test_simplifies_fraction(self):
        result = normalize_formula(r"\frac{a}{b}")
        assert "a/b" in result or "(a)/(b)" in result

    def test_simplifies_sqrt(self):
        result = normalize_formula(r"\sqrt[3]{x}")
        assert "\\sqrt{" in result
        assert "[3]" not in result

    def test_removes_display_math_delimiters(self):
        result = normalize_formula(r"\[\int_a^b f(x)dx\]")
        assert result

    def test_strips_dollar_delimiters(self):
        result = normalize_formula(r"$$E=mc^2$$")
        assert "E=mc" in result
        assert "$$" not in result

    def test_returns_empty_for_empty_input(self):
        assert normalize_formula("") == ""
        assert normalize_formula("   ") == ""

    def test_generalize_vars(self):
        result = normalize_formula(r"x^2 + y^2", generalize_vars=True)
        assert "V" in result


class TestExtractFormulas:
    def test_extracts_dollar_inline(self):
        formulas = extract_formulas("Formula $E=mc^2$ is famous.")
        assert "E=mc^2" in formulas

    def test_extracts_double_dollar(self):
        formulas = extract_formulas("Consider:\n$$\nE = mc^2\n$$")
        assert any("E = mc^2" in f for f in formulas)

    def test_extracts_equation_environment(self):
        formulas = extract_formulas(r"\begin{equation}a+b=c\end{equation}")
        assert any("a+b=c" in f for f in formulas)

    def test_returns_empty_for_plain_text(self):
        assert extract_formulas("This is plain text.") == []

    def test_extracts_multiple_formulas(self):
        text = r"First $a=1$, second $b=2$."
        formulas = extract_formulas(text)
        assert len(formulas) >= 2


class TestFormulaSimilarity:
    def test_identical_formulas(self):
        sim = formula_similarity(r"E=mc^2", r"E=mc^2")
        assert sim > 0.99

    def test_similar_formulas(self):
        sim = formula_similarity(r"E=mc^2", r"E = m c^2")
        assert sim > 0.5

    def test_dissimilar_formulas(self):
        sim = formula_similarity(r"E=mc^2", r"\int_a^b f(x)dx")
        assert sim < 0.5

    def test_empty_input(self):
        assert formula_similarity("", "") == 0.0
        assert formula_similarity("a", "") == 0.0
