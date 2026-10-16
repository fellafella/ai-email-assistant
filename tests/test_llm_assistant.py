from types import SimpleNamespace

import pytest
from google.genai import errors

from llm_assistant import LLMError, _extract_json, generate_with_llm, process_email
from models import Category, EmailInput, Priority

VALID = (
    '{"category": "Meeting", "priority": "High", '
    '"summary": "Asks for a call.", "reply_draft": "Hello, Tuesday works for me."}'
)


class FakeClient:
    """Faux client : aucun appel réseau, aucune clé API nécessaire."""

    def __init__(self, text: str | None = "", error: Exception | None = None):
        self._text, self._error = text, error
        self.models = self

    def generate_content(self, **kwargs):
        if self._error:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture
def email() -> EmailInput:
    return EmailInput(subject="Call", body="Can we have a call ASAP?")


def test_valid_response(email):
    r = generate_with_llm(email, FakeClient(VALID))
    assert r.source == "llm"
    assert r.category == Category.MEETING
    assert r.priority == Priority.HIGH
    assert r.approved is False  # jamais approuvé automatiquement


def test_json_in_code_fence(email):
    r = generate_with_llm(email, FakeClient(f"```json\n{VALID}\n```"))
    assert r.source == "llm"


def test_invalid_json_raises(email):
    with pytest.raises(LLMError):
        generate_with_llm(email, FakeClient("pas du json"))


def test_empty_response_raises(email):
    with pytest.raises(LLMError):
        generate_with_llm(email, FakeClient(None))


def test_invalid_category_raises(email):
    bad = VALID.replace("Meeting", "Spam")
    with pytest.raises(LLMError):
        generate_with_llm(email, FakeClient(bad))


def test_fallback_on_bad_json(email):
    r = process_email(email, FakeClient("oups"))
    assert r.source == "rules"
    assert r.priority == Priority.HIGH  # "ASAP" détecté par les règles


def test_fallback_on_api_error(email):
    err = errors.APIError(500, {"error": {"message": "boom"}})
    r = process_email(email, FakeClient(error=err))
    assert r.source == "rules"


def test_extract_json_no_braces():
    with pytest.raises(LLMError):
        _extract_json("hello")