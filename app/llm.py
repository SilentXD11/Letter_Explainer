"""LLM providers: Anthropic (Claude), OpenAI, and an offline rule-based fallback.

Every provider implements two things:
  * explain(text, facts, language) -> Explanation
  * transcribe_image(jpeg_bytes)   -> str   (only if supports_vision)

The offline provider needs no API key, so the app and the tests always run.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Protocol

from pydantic import ValidationError

from app.config import Settings
from app.schemas import Action, Deadline, Explanation, GlossaryItem

SYSTEM_PROMPT = """You help people understand official letters (from HMRC, councils, the NHS, \
DWP, energy companies, banks, landlords, courts, etc.). Many users are elderly, stressed, \
or not native English speakers.

Rules:
- Write the explanation in {language}, at a reading age of about 10: short sentences, no jargon.
- Only use facts that appear in the letter. Never invent dates, amounts, names or phone numbers.
  If something is unclear or missing (e.g. OCR errors), say so.
- The "facts detected by rules" are extracted deterministically from the letter. Prefer them for
  dates, amounts and reference numbers unless the letter clearly says otherwise.
- Put the most important thing first: what the letter wants the reader to DO and by WHEN.
- If the letter shows signs of being a scam (asks for bank details, PINs, gift cards, crypto,
  urgent payment to an unusual account), explain the warning signs in "scam_warning".
- "draft_reply" must be in English (it is sent to the organisation), polite, short, with
  [placeholders] for anything you don't know (name, address, account number).
- This is not legal or financial advice; suggest Citizens Advice for serious matters.

Respond with ONLY a JSON object, no markdown, with exactly these keys:
{{
  "summary": str,
  "sender": str | null,
  "letter_type": str,
  "urgency": "low" | "medium" | "high",
  "urgency_reason": str,
  "key_points": [str],
  "actions": [{{"action": str, "deadline": str | null}}],
  "deadlines": [{{"date": "YYYY-MM-DD", "description": str}}],
  "amounts": [str],
  "reference_numbers": [str],
  "glossary": [{{"term": str, "meaning": str}}],
  "scam_warning": str | null,
  "draft_reply": str
}}"""

TRANSCRIBE_PROMPT = (
    "This is a photo of a printed letter. Transcribe ALL of the text exactly as written, "
    "keeping line breaks and layout order. Do not summarise or correct anything. "
    "If a word is unreadable, write [unclear]. Output only the transcription."
)


class LLMError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    supports_vision: bool

    def explain(self, text: str, facts: dict, language: str = "English") -> Explanation: ...

    def transcribe_image(self, jpeg: bytes) -> str: ...


def build_user_prompt(text: str, facts: dict) -> str:
    return (
        "Facts detected by rules (may be incomplete):\n"
        f"{json.dumps(facts, indent=2, default=str)}\n\n"
        "Letter text (from OCR, may contain small errors):\n"
        f'"""\n{text[:20000]}\n"""'
    )


def parse_explanation(raw: str) -> Explanation:
    """Pull the JSON object out of the model's reply and validate it."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model did not return JSON")
    try:
        data = json.loads(cleaned[start: end + 1])
        if data.get("urgency") not in ("low", "medium", "high"):
            data["urgency"] = "medium"
        return Explanation(**{k: v for k, v in data.items() if v is not None or k in ("sender", "scam_warning")})
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


# --------------------------------------------------------------------------- #
# Offline (rule-based) provider
# --------------------------------------------------------------------------- #
class OfflineProvider:
    """Works without any API key. Less fluent, but never makes things up."""

    name = "offline"
    supports_vision = False

    def explain(self, text: str, facts: dict, language: str = "English") -> Explanation:
        deadlines = [
            Deadline(date=d["date"], description=d["context"][:200])
            for d in facts["dates"] if d["is_deadline"]
        ]
        actions: list[Action] = []
        for sentence in _sentences(text):
            low = sentence.lower()
            if re.search(r"\b(please|you must|you need to|you should|pay|call|contact|send|reply|bring)\b", low):
                deadline = next((d.date for d in deadlines if d.description and d.description in sentence), None)
                if deadline is None:
                    deadline = next((d["date"] for d in facts["dates"] if d["text"] in sentence), None)
                if deadline is None and (rel := re.search(r"within \d{1,3} (?:days?|weeks?|months?)", sentence, re.I)):
                    deadline = rel.group(0)
                actions.append(Action(action=sentence[:250], deadline=deadline))
        for rel in facts["relative_deadlines"]:
            phrase = re.search(r"within \d{1,3} \w+", rel, re.I)
            if phrase and not any(phrase.group(0).lower() in a.action.lower() for a in actions):
                actions.append(Action(action=rel[:250], deadline=phrase.group(0)))

        today = date.today().isoformat()
        upcoming = [d for d in deadlines if d.date >= today]
        sender = facts.get("sender") or "the sender"
        kind = facts["letter_type"].replace("_", " ")
        summary_parts = [f"This looks like a {kind} letter from {sender}."]
        if facts["amounts"]:
            summary_parts.append(f"It mentions {', '.join(a['amount'] for a in facts['amounts'][:3])}.")
        if upcoming:
            summary_parts.append(f"The next deadline is {_nice_date(upcoming[0].date)}.")
        elif deadlines:
            past = _nice_date(deadlines[-1].date)
            summary_parts.append(f"A date in the letter ({past}) has already passed, so act soon.")
        if facts["scam_signs"]:
            summary_parts.append("It shows signs of a scam, so don't pay or reply until you've checked it's real.")
        elif actions:
            summary_parts.append("See 'What you need to do' below.")
        if language.lower() != "english":
            summary_parts.append(f"(Offline mode can only explain in English, not {language}.)")

        scam = None
        if facts["scam_signs"]:
            scam = (
                "Be careful: this letter mentions " + ", ".join(facts["scam_signs"])
                + ". Real organisations rarely ask for these. Contact the organisation using a "
                "phone number from its official website, not the one in the letter."
            )

        return Explanation(
            summary=" ".join(summary_parts),
            sender=facts.get("sender"),
            letter_type=facts["letter_type"],
            urgency=facts["urgency"],
            urgency_reason=_urgency_reason(facts),
            key_points=[s[:250] for s in _sentences(text)[:5]],
            actions=actions[:6],
            deadlines=deadlines,
            amounts=[a["amount"] for a in facts["amounts"]],
            reference_numbers=facts["references"],
            glossary=_glossary(text),
            scam_warning=scam,
            draft_reply=_draft_reply(facts),
        )

    def transcribe_image(self, jpeg: bytes) -> str:  # pragma: no cover - never called
        raise LLMError("Offline mode cannot read images with AI. Add an API key to enable this.")


GLOSSARY = {
    "arrears": "money you owe that is already late",
    "liability order": "a court order saying you must pay; it allows the council to take stronger action",
    "enforcement agent": "another name for a bailiff",
    "direct debit": "an automatic payment taken from your bank account",
    "self assessment": "the yearly form some people fill in to tell HMRC about their income",
    "tax code": "a code your employer uses to work out how much tax to take from your pay",
    "pcn": "Penalty Charge Notice, a fine (often for parking)",
    "penalty charge notice": "a fine (often for parking or driving in a bus lane)",
    "instalment": "one of several smaller payments that together pay the full amount",
    "tariff": "the price plan for your gas or electricity",
    "summons": "an official order to go to court",
    "appeal": "asking for a decision to be looked at again",
    "mandatory reconsideration": "asking DWP to look at a benefits decision again before you can appeal",
    "discount": "a reduction in the amount you have to pay",
}


def _glossary(text: str) -> list[GlossaryItem]:
    low = text.lower()
    return [GlossaryItem(term=t, meaning=m) for t, m in GLOSSARY.items() if t in low]


def _sentences(text: str) -> list[str]:
    """Split into sentences paragraph by paragraph, skipping address/header lines."""
    # OCR sometimes breaks a paragraph in the middle of a sentence: glue those back.
    paras: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if paras and paras[-1].rstrip()[-1:] not in ".!?:":
            paras[-1] += " " + para
        else:
            paras.append(para)
    out: list[str] = []
    for para in paras:
        flat = " ".join(para.split())
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", flat):
            n = len(part.split())
            if 4 <= n <= 45 and part.rstrip()[-1:] in ".!?":
                out.append(part.strip())
    return out


def _nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def _urgency_reason(facts: dict) -> str:
    if facts["urgency"] == "high":
        return (
            "The letter uses serious wording (e.g. final notice, court, enforcement) "
            "or has a deadline within 14 days."
        )
    if facts["urgency"] == "medium":
        return "The letter asks you to do something or has a deadline."
    return "No deadline or urgent wording was found."


def _draft_reply(facts: dict) -> str:
    ref = facts["references"][0] if facts["references"] else "[reference number]"
    return (
        "Dear Sir or Madam,\n\n"
        f"Reference: {ref}\n\n"
        "I have received your letter and I would like to [ask for more information / arrange a "
        "payment plan / confirm that I have paid / ask for more time]. [Add details here.]\n\n"
        "Please reply to me at the address above or by email at [your email].\n\n"
        "Yours faithfully,\n[Your full name]\n[Your address]"
    )


# --------------------------------------------------------------------------- #
# Anthropic (Claude)
# --------------------------------------------------------------------------- #
class AnthropicProvider:
    name = "anthropic"
    supports_vision = True

    def __init__(self, model: str):
        import anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model

    def _complete(self, system: str | None, content: list | str, max_tokens: int) -> str:
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
        if system:
            kwargs["system"] = system
        try:
            msg = self.client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic API error: {exc}") from exc
        return "".join(getattr(b, "text", "") for b in msg.content)

    def explain(self, text: str, facts: dict, language: str = "English") -> Explanation:
        raw = self._complete(SYSTEM_PROMPT.format(language=language), build_user_prompt(text, facts), 2500)
        return parse_explanation(raw)

    def transcribe_image(self, jpeg: bytes) -> str:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpeg).decode()}},
            {"type": "text", "text": TRANSCRIBE_PROMPT},
        ]
        return self._complete(None, content, 4000).strip()


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #
class OpenAIProvider:
    name = "openai"
    supports_vision = True

    def __init__(self, model: str):
        import openai

        self.client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.model = model

    def _chat(self, messages: list, json_mode: bool) -> str:
        kwargs = {"model": self.model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"OpenAI API error: {exc}") from exc
        return resp.choices[0].message.content or ""

    def explain(self, text: str, facts: dict, language: str = "English") -> Explanation:
        raw = self._chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
                {"role": "user", "content": build_user_prompt(text, facts)},
            ],
            json_mode=True,
        )
        return parse_explanation(raw)

    def transcribe_image(self, jpeg: bytes) -> str:
        url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        return self._chat(
            [{"role": "user", "content": [
                {"type": "text", "text": TRANSCRIBE_PROMPT},
                {"type": "image_url", "image_url": {"url": url}},
            ]}],
            json_mode=False,
        ).strip()


def get_provider(settings: Settings) -> Provider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_model)
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings.openai_model)
    return OfflineProvider()
