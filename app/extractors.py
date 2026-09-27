"""Rule-based extraction of the facts that matter most in a letter.

These rules run on every letter, even when an LLM is used, because:
  * they are deterministic, so dates and amounts are never "hallucinated";
  * they are passed to the LLM as hints and used to double-check its output;
  * they power the offline mode (no API key needed) and the automated tests.
"""

from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)

DATE_PATTERNS = [
    # 12 October 2026 / 12th Oct 2026
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\.?,?\s+(\d{{4}})\b", re.I),
    # October 12, 2026
    re.compile(rf"\b({MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
    # 12/10/2026 or 12-10-2026 or 12.10.2026 (UK order: day first)
    re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"),
]

DEADLINE_WORDS = re.compile(
    r"\b(by|before|no later than|due|deadline|until|pay|respond|reply|must|within|expires?|appointment)\b",
    re.I,
)
RELATIVE_DEADLINE = re.compile(r"\bwithin\s+(\d{1,3})\s+(days?|weeks?|months?)\b", re.I)
AMOUNT = re.compile(r"(£\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\bGBP\s?\d+(?:\.\d{2})?)", re.I)
REFERENCE = re.compile(
    r"\b(?:reference|ref|account|customer|case|claim|invoice|policy|penalty charge notice|pcn)"
    r"(?:\s+(?:number|no\.?))?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{4,20}[A-Z0-9])\b",
    re.I,
)

HIGH_URGENCY = [
    "final notice", "final reminder", "court", "bailiff", "enforcement agent", "enforcement",
    "legal action", "county court judgment", "ccj", "disconnect", "summons", "liability order",
    "debt collection", "penalty", "overdue", "arrears", "eviction", "possession",
]
MEDIUM_URGENCY = [
    "reminder", "payment due", "please respond", "action required", "must", "deadline",
    "appointment", "renewal", "review of your",
]
SCAM_SIGNS = [
    "gift card", "itunes", "bitcoin", "crypto", "wire transfer", "western union",
    "confirm your bank details", "your pin", "password", "click the link", "act now or",
]

LETTER_TYPES = {
    "tax": ["hmrc", "self assessment", "tax code", "tax return", "national insurance"],
    "council_tax": ["council tax"],
    "benefits": ["dwp", "universal credit", "pip", "personal independence", "jobcentre", "pension credit"],
    "energy_bill": ["electricity", "gas", "energy", "meter reading", "kwh", "tariff"],
    "health": ["nhs", "gp surgery", "hospital", "appointment", "clinic", "prescription"],
    "parking_fine": ["penalty charge", "pcn", "parking", "contravention"],
    "housing": ["tenancy", "landlord", "rent", "housing association", "section 21", "section 8"],
    "bank_or_debt": ["bank", "overdraft", "credit card", "loan", "debt", "arrears"],
    "immigration_or_visa": ["home office", "visa", "biometric residence", "brp"],
    "tv_licence": ["tv licence", "tv licensing"],
}

KNOWN_SENDERS = [
    "HMRC", "HM Revenue and Customs", "DWP", "Department for Work and Pensions", "NHS",
    "Home Office", "DVLA", "TV Licensing", "Council", "British Gas", "EDF", "Octopus Energy",
    "E.ON", "OVO", "Thames Water", "Royal Mail", "HM Courts", "Student Loans Company",
]

_MONTH_INDEX = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _month_num(name: str) -> int:
    return _MONTH_INDEX[name.lower()[:3]]


_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|\n\s*\n")


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing text[start:end]. A '.' only ends a sentence when
    followed by whitespace, so amounts like £142.50 don't split it."""
    left = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        left = m.end()
    m = _SENTENCE_END.search(text, end)
    right = m.end() if m else len(text)
    return " ".join(text[left:right].split())


def find_dates(text: str) -> list[dict]:
    """Return dates found in the text with the sentence they appear in."""
    found: list[dict] = []
    seen: set[tuple[date, int]] = set()
    for i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            try:
                if i == 0:
                    d = date(int(m.group(3)), _month_num(m.group(2)), int(m.group(1)))
                elif i == 1:
                    d = date(int(m.group(3)), _month_num(m.group(1)), int(m.group(2)))
                else:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except (ValueError, KeyError):
                continue
            key = (d, m.start())
            if key in seen:
                continue
            seen.add(key)
            context = _sentence_around(text, m.start(), m.end())
            found.append({
                "date": d.isoformat(),
                "text": m.group(0),
                "context": context,
                "is_deadline": bool(DEADLINE_WORDS.search(context)),
            })
    found.sort(key=lambda x: x["date"])
    return found


def find_relative_deadlines(text: str) -> list[str]:
    return [_sentence_around(text, m.start(), m.end()) for m in RELATIVE_DEADLINE.finditer(text)]


def find_amounts(text: str) -> list[dict]:
    out, seen = [], set()
    for m in AMOUNT.finditer(text):
        amount = m.group(0).replace(" ", "")
        if amount in seen:
            continue
        seen.add(amount)
        out.append({"amount": amount, "context": _sentence_around(text, m.start(), m.end())})
    return out


def find_references(text: str) -> list[str]:
    refs: list[str] = []
    for m in REFERENCE.finditer(text):
        ref = m.group(1).strip()
        if ref not in refs and any(c.isdigit() for c in ref):
            refs.append(ref)
    return refs


def classify_letter(text: str) -> str:
    low = text.lower()
    scores = {k: sum(low.count(w) for w in words) for k, words in LETTER_TYPES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def guess_sender(text: str) -> str | None:
    head = "\n".join(text.splitlines()[:15])
    for name in KNOWN_SENDERS:
        m = re.search(rf"([A-Z][\w&'\- ]{{0,40}}{re.escape(name)}[\w ]{{0,20}})", head)
        if m:
            return " ".join(m.group(1).split())
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[0][:80] if lines else None


def urgency_level(text: str, dates: list[dict], today: date | None = None) -> str:
    low = text.lower()
    today = today or date.today()
    if any(w in low for w in HIGH_URGENCY):
        return "high"
    for d in dates:
        if d["is_deadline"]:
            days_left = (datetime.fromisoformat(d["date"]).date() - today).days
            if 0 <= days_left <= 14:
                return "high"
    if any(w in low for w in MEDIUM_URGENCY) or any(d["is_deadline"] for d in dates):
        return "medium"
    return "low"


def scam_warnings(text: str) -> list[str]:
    low = text.lower()
    return [w for w in SCAM_SIGNS if w in low]


def extract_facts(text: str, today: date | None = None) -> dict:
    dates = find_dates(text)
    return {
        "letter_type": classify_letter(text),
        "sender": guess_sender(text),
        "dates": dates,
        "relative_deadlines": find_relative_deadlines(text),
        "amounts": find_amounts(text),
        "references": find_references(text),
        "urgency": urgency_level(text, dates, today),
        "scam_signs": scam_warnings(text),
    }
