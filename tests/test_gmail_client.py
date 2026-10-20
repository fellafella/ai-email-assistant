import base64
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gmail_client import (
    GmailError,
    GmailMessage,
    build_reply,
    create_draft_reply,
    fetch_unread,
    is_no_reply,
    parse_message,
    skip_reason,
)
from models import EmailInput

ROOT = Path(__file__).resolve().parent.parent


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def raw_message(payload: dict, msg_id: str = "m1") -> dict:
    return {"id": msg_id, "threadId": "t1", "snippet": "snip", "payload": payload}


HEADERS = [
    {"name": "From", "value": "Alice <alice@example.com>"},
    {"name": "Subject", "value": "Meeting tomorrow"},
    {"name": "Message-ID", "value": "<abc@mail>"},
]


def test_parse_plain_text():
    msg = parse_message(raw_message({
        "mimeType": "text/plain", "headers": HEADERS, "body": {"data": b64("Hello Bob")},
    }))
    assert msg.email.body == "Hello Bob"
    assert msg.email.subject == "Meeting tomorrow"
    assert msg.reply_to == "alice@example.com"
    assert msg.thread_id == "t1"


def test_multipart_prefers_plain_text():
    payload = {
        "mimeType": "multipart/alternative", "headers": HEADERS,
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>HTML version</p>")}},
            {"mimeType": "text/plain", "body": {"data": b64("Plain version")}},
        ],
    }
    assert parse_message(raw_message(payload)).email.body == "Plain version"


def test_html_fallback_strips_tags():
    payload = {
        "mimeType": "text/html", "headers": HEADERS,
        "body": {"data": b64("<style>x{}</style><p>Hello <b>world</b></p>")},
    }
    assert parse_message(raw_message(payload)).email.body == "Hello world"


def test_empty_body_falls_back_to_snippet():
    msg = parse_message(raw_message({"mimeType": "text/plain", "headers": HEADERS, "body": {}}))
    assert msg.email.body == "snip"


def make_msg(**overrides) -> GmailMessage:
    data = dict(
        gmail_id="m1", thread_id="t1", message_id="<abc@mail>",
        reply_to="alice@example.com",
        email=EmailInput(subject="Meeting tomorrow", body="Hi"),
    )
    data.update(overrides)
    return GmailMessage(**data)


def test_reply_subject_and_threading():
    reply = build_reply(make_msg(), "Sure!")
    assert reply["Subject"] == "Re: Meeting tomorrow"
    assert reply["In-Reply-To"] == "<abc@mail>"
    assert reply["To"] == "alice@example.com"


def test_reply_subject_not_doubled():
    msg = make_msg(email=EmailInput(subject="Re: Meeting", body="Hi"))
    assert build_reply(msg, "ok")["Subject"] == "Re: Meeting"


def test_create_draft_uses_only_drafts_create():
    service = MagicMock()
    service.users().drafts().create().execute.return_value = {"id": "d42"}
    service.reset_mock()
    service.users().drafts().create().execute.return_value = {"id": "d42"}

    assert create_draft_reply(service, make_msg(), "Sure!") == "d42"
    calls = " ".join(str(c) for c in service.mock_calls)
    assert "drafts" in calls and "create" in calls
    assert "send" not in calls.lower()


def test_create_draft_requires_recipient():
    with pytest.raises(GmailError):
        create_draft_reply(MagicMock(), make_msg(reply_to=""), "x")


def test_header_injection_is_rejected():
    msg = make_msg(email=EmailInput(subject="Hi\nBcc: evil@example.com", body="x"))
    with pytest.raises(GmailError):
        create_draft_reply(MagicMock(), msg, "x")


def test_fetch_unread():
    service = MagicMock()
    users = service.users.return_value
    users.messages.return_value.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
    users.messages.return_value.get.return_value.execute.return_value = raw_message(
        {"mimeType": "text/plain", "headers": HEADERS, "body": {"data": b64("Hello")}}
    )
    result = fetch_unread(service, max_results=1)
    assert len(result) == 1 and result[0].email.body == "Hello"


def test_code_never_sends_emails():
    """Garde-fou : aucun appel d'envoi Gmail ne doit exister dans le projet."""
    forbidden = re.compile(r"\.send\(|messages\(\)\s*\.send|drafts\(\)\s*\.send")
    for name in ("gmail_client.py", "demo_gmail.py", "app.py", "llm_assistant.py"):
        path = ROOT / name
        if not path.exists():  # app.py n'existe pas encore avant la Phase 3
            continue
        assert not forbidden.search(path.read_text(encoding="utf-8")), (
            f"Appel d'envoi trouvé dans {name}"
        )


def test_is_no_reply():
    assert is_no_reply("no-reply@accounts.google.com")
    assert is_no_reply("noreply@github.com")
    assert is_no_reply("do_not_reply@bank.com")
    assert not is_no_reply("alice@example.com")


def test_no_reply_draft_refused():
    with pytest.raises(GmailError):
        create_draft_reply(MagicMock(), make_msg(reply_to="no-reply@x.com"), "x")
def plain_payload(headers):
    return {"mimeType": "text/plain", "headers": headers, "body": {"data": b64("Promo")}}


def test_newsletter_detected_by_list_unsubscribe():
    headers = HEADERS + [{"name": "List-Unsubscribe", "value": "<mailto:u@x.com>"}]
    msg = parse_message(raw_message(plain_payload(headers)))
    assert msg.is_automated
    assert skip_reason(msg) is not None


def test_promotions_label_detected():
    raw = raw_message(plain_payload(HEADERS))
    raw["labelIds"] = ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"]
    assert parse_message(raw).is_automated


def test_auto_submitted_header_detected():
    headers = HEADERS + [{"name": "Auto-Submitted", "value": "auto-generated"}]
    assert parse_message(raw_message(plain_payload(headers))).is_automated


def test_normal_email_is_not_automated():
    msg = parse_message(raw_message(plain_payload(HEADERS)))
    assert not msg.is_automated
    assert skip_reason(msg) is None


def test_automated_draft_refused():
    with pytest.raises(GmailError):
        create_draft_reply(MagicMock(), make_msg(is_automated=True), "x")
                