from backend.rag.glossary_extractor import extract_glossary, has_glossary


class TestExtractGlossary:
    def test_definition_acronym(self):
        result = extract_glossary("Long Short-Term Memory (LSTM) is a type of RNN.")
        terms = [g.term for g in result]
        assert "LSTM" in terms

    def test_acronym_definition(self):
        result = extract_glossary("RNN: Recurrent Neural Network.")
        terms = [g.term for g in result]
        assert "RNN" in terms

    def test_deduplicates(self):
        text = "First mention: Long Short-Term Memory (LSTM). Later mention of LSTM again."
        result = extract_glossary(text)
        terms = [g.term for g in result]
        assert "LSTM" in terms
        assert terms.count("LSTM") == 1

    def test_plain_text_no_glossary(self):
        assert extract_glossary("This is just plain text without acronyms.") == []

    def test_multiple_glossary_entries(self):
        text = "Recurrent Neural Network (RNN). Generative Adversarial Network (GAN)."
        result = extract_glossary(text)
        terms = [g.term for g in result]
        assert "RNN" in terms
        assert "GAN" in terms


class TestHasGlossary:
    def test_has_definition_acronym(self):
        assert has_glossary("Attention Is All You Need (AIAYN).")

    def test_no_glossary(self):
        assert not has_glossary("Just plain text.")
