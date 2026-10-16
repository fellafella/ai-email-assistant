"""Démo Phase 2 : analyse par LLM + brouillon de réponse (rien n'est envoyé)."""
import logging

from pydantic import ValidationError

from llm_assistant import process_email
from models import EmailInput

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SAMPLES: list[dict[str, str]] = [
    {
        "sender": "hr@techcorp.com",
        "subject": "Interview for the Python Developer position",
        "body": "Hello, we reviewed your CV and would like to invite you to an interview next week. Are you available Tuesday or Wednesday?",
    },
    {
        "sender": "accounting@supplier.com",
        "subject": "URGENT: Invoice 2041 overdue",
        "body": "Your payment is overdue. Please transfer the amount today.",
    },
]


def main() -> None:
    for raw in SAMPLES:
        try:
            email = EmailInput(**raw)
        except ValidationError as exc:
            print(f"Email invalide: {exc.errors()[0]['msg']}")
            continue

        result = process_email(email)
        print(f"\n=== {email.subject} ===")
        print(f"Source    : {result.source}")
        print(f"Catégorie : {result.category.value}")
        print(f"Priorité  : {result.priority.value}")
        print(f"Résumé    : {result.summary}")
        if result.reply_draft:
            print(f"\n--- Brouillon (NON envoyé, en attente de ton approbation) ---\n{result.reply_draft}")


if __name__ == "__main__":
    main()