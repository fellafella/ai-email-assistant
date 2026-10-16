"""Analyse d'e-mails basée sur des règles (Phase 1)."""
import logging
import re

from models import Category, EmailAnalysis, EmailInput, Priority

logger = logging.getLogger(__name__)

# L'ordre sert de départage en cas d'égalité de score.
CATEGORY_KEYWORDS: dict[Category, list[str]] = {
    Category.RECRUITMENT: [
        "job", "position", "candidate", "interview", "recruiter", "resume",
        "cv", "hiring", "application", "vacancy", "job offer", "opportunity",
    ],
    Category.MEETING: [
        "meeting", "schedule", "calendar", "call", "appointment",
        "availability", "zoom", "teams", "invite", "catch up",
    ],
    Category.FINANCE: [
        "invoice", "payment", "bank", "budget", "tax", "receipt",
        "refund", "transfer", "billing", "overdue",
    ],
}

PRIORITY_KEYWORDS: list[str] = [
    "urgent", "asap", "as soon as possible", "immediately", "deadline",
    "today", "by tomorrow", "by end of day", "eod", "time-sensitive",
    "right away",
]


def _find_keywords(text: str, keywords: list[str]) -> list[str]:
    """Retourne les mots-clés présents dans le texte (mots entiers)."""
    found: list[str] = []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw) + r"s?\b"
        if re.search(pattern, text):
            found.append(kw)
    return found


def analyze_email(email: EmailInput) -> EmailAnalysis:
    """Classe l'e-mail et détecte sa priorité."""
    text = f"{email.subject} {email.body}".lower()

    best_category = Category.GENERAL
    best_matches: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        matches = _find_keywords(text, keywords)
        if len(matches) > len(best_matches):
            best_category, best_matches = category, matches

    priority_matches = _find_keywords(text, PRIORITY_KEYWORDS)
    priority = Priority.HIGH if priority_matches else Priority.NORMAL

    analysis = EmailAnalysis(
        category=best_category,
        priority=priority,
        category_keywords=best_matches,
        priority_keywords=priority_matches,
    )
    logger.info("Analyse: %s / %s", analysis.category.value, analysis.priority.value)
    return analysis