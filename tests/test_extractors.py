from datetime import date

from app.extractors import extract_facts, find_amounts, find_dates, find_references, urgency_level


def test_dates_in_several_formats():
    text = "Pay by 5 October 2026. Appointment on 12/11/2026. Due March 3rd, 2027."
    dates = {d["date"] for d in find_dates(text)}
    assert {"2026-10-05", "2026-11-12", "2027-03-03"} <= dates


def test_amount_with_decimals_does_not_break_sentence():
    text = "You owe £142.50 for this month. Total is £1,282.50."
    amounts = find_amounts(text)
    assert [a["amount"] for a in amounts] == ["£142.50", "£1,282.50"]
    assert amounts[0]["context"] == "You owe £142.50 for this month."


def test_reference_numbers():
    assert find_references("Account number: CT-4829-1173\nRef: AB123456C") == ["CT-4829-1173", "AB123456C"]


def test_full_letter_facts(letter_text):
    facts = extract_facts(letter_text, today=date(2026, 9, 27))
    assert facts["letter_type"] == "council_tax"
    assert facts["sender"] == "Riverside Borough Council"
    assert "CT-4829-1173" in facts["references"]
    assert facts["urgency"] == "high"
    deadlines = [d["date"] for d in facts["dates"] if d["is_deadline"]]
    assert "2026-10-05" in deadlines
    assert facts["scam_signs"] == []


def test_urgency_low_for_plain_information():
    text = "We are writing to let you know that our office has moved to a new address."
    assert urgency_level(text, [], today=date(2026, 1, 1)) == "low"


def test_scam_signs_detected():
    facts = extract_facts("HMRC: you are owed a refund. Pay the fee with an iTunes gift card today.")
    assert "gift card" in facts["scam_signs"]
