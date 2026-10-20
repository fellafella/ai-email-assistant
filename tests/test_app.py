from pathlib import Path

import gmail_client
import llm_assistant
import pytest
from gmail_client import GmailMessage
from models import Category, EmailInput, EmailResult, Priority
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def fake_process(email):
    return EmailResult(
        category=Category.MEETING,
        priority=Priority.HIGH,
        summary="Asks for a call.",
        reply_draft="Hello, Tuesday works.",
        source="llm",
    )


def gmail_message(**overrides) -> GmailMessage:
    data = dict(
        gmail_id="m1", thread_id="t1", reply_to="alice@example.com",
        email=EmailInput(sender="Alice <alice@example.com>", subject="Call", body="Can we talk ASAP?"),
    )
    data.update(overrides)
    return GmailMessage(**data)


@pytest.fixture
def gmail(monkeypatch):
    """Remplace Gmail et le LLM par de faux objets (aucun réseau)."""
    saved = []
    monkeypatch.setattr(llm_assistant, "process_email", fake_process)
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    monkeypatch.setattr(gmail_client, "fetch_unread", lambda service, max_results=10: [gmail_message()])
    monkeypatch.setattr(
        gmail_client, "create_draft_reply",
        lambda service, msg, text: saved.append((msg.thread_id, text)) or "d1",
    )
    return saved


def test_empty_body_shows_error():
    at = AppTest.from_file(APP).run()
    at.button(key="analyze_btn").click().run()
    assert at.error and "vide" in at.error[0].value


def test_manual_flow_requires_review_before_approval(monkeypatch):
    monkeypatch.setattr(llm_assistant, "process_email", fake_process)
    at = AppTest.from_file(APP).run()
    at.text_area(key="body").set_value("Can we have a call ASAP?")
    at.button(key="analyze_btn").click().run()

    assert at.text_area(key="draft").value == "Hello, Tuesday works."
    assert at.button(key="approve_btn").disabled  # impossible sans relecture

    at.checkbox(key="reviewed").check().run()
    at.button(key="approve_btn").click().run()
    assert at.session_state["approved"] is True
    assert "save_btn" not in [b.key for b in at.button]  # pas de Gmail en mode manuel

    at.text_area(key="draft").set_value("Autre texte").run()
    assert at.session_state["approved"] is False


def test_gmail_flow_saves_draft_only_after_approval(gmail):
    at = AppTest.from_file(APP).run()
    at.button(key="load_btn").click().run()
    at.selectbox(key="picked").select_index(0).run()
    assert at.text_area(key="body").value == "Can we talk ASAP?"

    at.button(key="analyze_btn").click().run()
    at.checkbox(key="reviewed").check().run()
    assert "save_btn" not in [b.key for b in at.button]  # pas avant l'approbation

    at.button(key="approve_btn").click().run()
    at.button(key="save_btn").click().run()
    assert gmail == [("t1", "Hello, Tuesday works.")]
    assert at.session_state["draft_id"] == "d1"


def test_automated_message_is_not_analyzed(gmail, monkeypatch):
    monkeypatch.setattr(
        gmail_client, "fetch_unread",
        lambda service, max_results=10: [gmail_message(is_automated=True)],
    )

    def boom(email):
        raise AssertionError("Le LLM ne doit pas être appelé")

    monkeypatch.setattr(llm_assistant, "process_email", boom)
    at = AppTest.from_file(APP).run()
    at.button(key="load_btn").click().run()
    at.selectbox(key="picked").select_index(0).run()
    at.button(key="analyze_btn").click().run()
    assert at.session_state["result"] is None
    assert at.info and "automatique" in at.info[0].value


def test_manual_edit_detaches_gmail_message(gmail):
    at = AppTest.from_file(APP).run()
    at.button(key="load_btn").click().run()
    at.selectbox(key="picked").select_index(0).run()
    assert at.session_state["gmail_msg"] is not None
    at.text_input(key="subject").set_value("Autre objet").run()
    assert at.session_state["gmail_msg"] is None