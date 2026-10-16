"""Point d'entrée : démonstration de l'analyse sur des e-mails d'exemple."""
import logging

from pydantic import ValidationError

from email_assistant import analyze_email
from models import EmailInput

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SAMPLES: list[dict[str, str]] = [
    {
        "subject": "Interview for the Python Developer position",
        "body": "Hello, we reviewed your CV and would like to invite you to an interview.",
    },
    {
        "subject": "Team meeting tomorrow",
        "body": "Can we schedule a call to discuss the project? Please confirm your availability.",
    },
    {
        "subject": "URGENT: Invoice overdue",
        "body": "Your payment is overdue. Please transfer the amount ASAP.",
    },
    {
        "subject": "Hello",
        "body": "Just wanted to say hi and share some news about the holidays.",
    },
    {"subject": "Empty", "body": "   "},  # e-mail invalide
]


def main() -> None:
    for i, raw in enumerate(SAMPLES, start=1):
        print(f"\n--- Email {i}: {raw['subject']} ---")
        try:
            email = EmailInput(**raw)
        except ValidationError as exc:
            print(f"Email invalide ignoré: {exc.errors()[0]['msg']}")
            continue
        result = analyze_email(email)
        print(f"Catégorie : {result.category.value}")
        print(f"Priorité  : {result.priority.value}")
        print(f"Mots-clés : {result.category_keywords} | {result.priority_keywords}")


if __name__ == "__main__":
    main()