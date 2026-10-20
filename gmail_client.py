"""Intégration Gmail (Phase 4) : lecture des e-mails et création de BROUILLONS.

Sécurité : ce module n'envoie jamais d'e-mail. Il n'utilise que la création de
brouillons ; aucun appel d'envoi n'existe dans le code (un test le vérifie).
"""
import base64
import logging
import re
from email.message import EmailMessage
from email.utils import parseaddr
from html import unescape
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

from models import EmailInput

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # lire les e-mails
    "https://www.googleapis.com/auth/gmail.compose",   # créer des brouillons
]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"  # téléchargé depuis Google Cloud
TOKEN_FILE = BASE_DIR / "token.json"              # créé après la 1re connexion
MAX_BODY_CHARS = 5000  # limite envoyée au LLM

# NOUVEAU : adresses automatiques auxquelles on ne répond pas
NO_REPLY_PATTERN = re.compile(
    r"no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon", re.IGNORECASE
)


class GmailError(Exception):
    """Erreur liée à Gmail (authentification, API, fichiers manquants)."""


class GmailMessage(BaseModel):
    """E-mail Gmail converti, avec ce qu'il faut pour répondre dans le même fil."""

    gmail_id: str
    thread_id: str
    message_id: str = ""   # en-tête Message-ID
    references: str = ""
    reply_to: str = ""     # adresse du destinataire de la réponse
    email: EmailInput


# NOUVEAU
def is_no_reply(address: str) -> bool:
    """True si l'adresse est automatique (no-reply, mailer-daemon...)."""
    return bool(NO_REPLY_PATTERN.search(address))


# --- Authentification ---------------------------------------------------------
def get_service() -> Any:
    """Se connecte à Gmail via OAuth (ouvre le navigateur à la 1re utilisation)."""
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            logger.warning("Autorisation expirée, nouvelle connexion nécessaire.")
            creds = None

    if not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            raise GmailError(
                "credentials.json introuvable à la racine du projet "
                "(voir la configuration Google Cloud)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


# --- Lecture ------------------------------------------------------------------
def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _find_part(payload: dict[str, Any], mime_type: str) -> str | None:
    if payload.get("mimeType") == mime_type and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts") or []:
        found = _find_part(part, mime_type)
        if found:
            return found
    return None


def _extract_body(payload: dict[str, Any]) -> str:
    """Préfère le texte brut ; sinon nettoie le HTML."""
    text = _find_part(payload, "text/plain")
    if text:
        return text.strip()
    html = _find_part(payload, "text/html")
    if html:
        html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S | re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", unescape(html)).strip()
    return ""


def parse_message(raw: dict[str, Any]) -> GmailMessage:
    """Convertit la réponse brute de l'API Gmail en GmailMessage."""
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_body(payload) or raw.get("snippet", "") or "(message vide)"
    return GmailMessage(
        gmail_id=raw["id"],
        thread_id=raw.get("threadId", ""),
        message_id=headers.get("message-id", ""),
        references=headers.get("references", ""),
        reply_to=parseaddr(headers.get("reply-to") or headers.get("from", ""))[1],
        email=EmailInput(
            sender=headers.get("from"),
            subject=headers.get("subject", ""),
            body=body[:MAX_BODY_CHARS],
        ),
    )


def fetch_unread(service: Any, max_results: int = 5) -> list[GmailMessage]:
    """Récupère les derniers e-mails non lus de la boîte de réception."""
    try:
        listing = (
            service.users().messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
            .execute()
        )
        messages: list[GmailMessage] = []
        for item in listing.get("messages", []):
            raw = (
                service.users().messages()
                .get(userId="me", id=item["id"], format="full")
                .execute()
            )
            messages.append(parse_message(raw))
        return messages
    except HttpError as exc:
        raise GmailError(f"Erreur Gmail: {exc}") from exc


# --- Brouillons (JAMAIS d'envoi) -----------------------------------------------
def build_reply(msg: GmailMessage, reply_text: str) -> EmailMessage:
    """Construit la réponse (dans le même fil de discussion)."""
    subject = msg.email.subject
    reply = EmailMessage()
    reply["To"] = msg.reply_to
    reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if msg.message_id:
        reply["In-Reply-To"] = msg.message_id
        reply["References"] = f"{msg.references} {msg.message_id}".strip()
    reply.set_content(reply_text)
    return reply


def create_draft_reply(service: Any, msg: GmailMessage, reply_text: str) -> str:
    """Crée un brouillon dans Gmail et renvoie son identifiant. N'envoie rien."""
    if not msg.reply_to:
        raise GmailError("Adresse du destinataire introuvable.")
    # NOUVEAU : pas de brouillon vers une adresse automatique
    if is_no_reply(msg.reply_to):
        raise GmailError("Cette adresse n'accepte pas de réponses (no-reply).")
    try:
        reply = build_reply(msg, reply_text)
    except ValueError as exc:  # en-tête invalide (ex: retour à la ligne injecté)
        raise GmailError(f"En-tête d'e-mail invalide: {exc}") from exc

    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
    try:
        draft = (
            service.users().drafts()
            .create(userId="me", body={"message": {"raw": raw, "threadId": msg.thread_id}})
            .execute()
        )
    except HttpError as exc:
        raise GmailError(f"Erreur Gmail: {exc}") from exc
    return draft["id"]