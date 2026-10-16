import pytest
from pydantic import ValidationError

from email_assistant import analyze_email
from models import Category, EmailInput, Priority


def make(subject: str, body: str) -> EmailInput:
    return EmailInput(subject=subject, body=body)


def test_recruitment():
    r = analyze_email(make("Job offer", "We have a position for a candidate like you."))
    assert r.category == Category.RECRUITMENT


def test_meeting():
    r = analyze_email(make("Meeting", "Let's schedule a call, check your availability."))
    assert r.category == Category.MEETING


def test_finance():
    r = analyze_email(make("Invoice", "Your payment and receipt are attached."))
    assert r.category == Category.FINANCE


def test_general_fallback():
    r = analyze_email(make("Hi", "Hope you are doing well."))
    assert r.category == Category.GENERAL
    assert r.priority == Priority.NORMAL


def test_high_priority():
    r = analyze_email(make("Report", "Please send it ASAP, the deadline is today."))
    assert r.priority == Priority.HIGH
    assert "asap" in r.priority_keywords


def test_normal_priority():
    r = analyze_email(make("Report", "Send it whenever you can."))
    assert r.priority == Priority.NORMAL


def test_whole_word_matching():
    r = analyze_email(make("Trip", "Our steamship leaves at noon."))
    assert r.category == Category.GENERAL


def test_empty_body_rejected():
    with pytest.raises(ValidationError):
        EmailInput(subject="x", body="   ")


def test_case_insensitive():
    r = analyze_email(make("URGENT", "INVOICE OVERDUE"))
    assert r.category == Category.FINANCE
    assert r.priority == Priority.HIGH