import pytest

from app.extractors import extract_facts
from app.llm import LLMError, OfflineProvider, parse_explanation
from app.pipeline import explain_text


def test_parse_json_inside_markdown_fence():
    raw = '```json\n{"summary": "A council tax reminder.", "urgency": "high", "actions": '\
          '[{"action": "Pay £142.50", "deadline": "2026-10-05"}], "sender": null}\n```'
    exp = parse_explanation(raw)
    assert exp.urgency == "high"
    assert exp.actions[0].deadline == "2026-10-05"


def test_invalid_urgency_is_normalised():
    assert parse_explanation('{"summary": "x", "urgency": "URGENT!!"}').urgency == "medium"


def test_non_json_raises():
    with pytest.raises(LLMError):
        parse_explanation("Sorry, I can't help with that.")


def test_offline_explanation(letter_text):
    exp = OfflineProvider().explain(letter_text, extract_facts(letter_text))
    assert "Riverside Borough Council" in exp.summary
    assert "£142.50" in exp.amounts
    assert any(a.deadline == "2026-10-05" for a in exp.actions)
    assert "CT-4829-1173" in exp.draft_reply
    assert any(g.term == "liability order" for g in exp.glossary)


class BrokenProvider:
    name = "broken"
    supports_vision = False

    def explain(self, text, facts, language="English"):
        raise LLMError("API down")


def test_falls_back_to_offline_when_llm_fails(letter_text):
    exp, used = explain_text(letter_text, "English", BrokenProvider())
    assert used == "offline (fallback)"
    assert exp.reference_numbers == ["CT-4829-1173"]
