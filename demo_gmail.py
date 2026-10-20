"""Démo Phase 4 : lit les e-mails non lus, génère une réponse, crée un BROUILLON Gmail.

Rien n'est envoyé : tu relis et envoies toi-même depuis Gmail (dossier Brouillons).
"""
import logging

# NOUVEAU : is_no_reply ajouté à l'import
from gmail_client import GmailError, create_draft_reply, fetch_unread, get_service, is_no_reply
from llm_assistant import process_email

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def main() -> None:
    try:
        service = get_service()
        messages = fetch_unread(service, max_results=3)
    except GmailError as exc:
        print(f"Erreur: {exc}")
        return

    if not messages:
        print("Aucun e-mail non lu.")
        return

    for msg in messages:
        # NOUVEAU : on ignore les adresses automatiques AVANT d'appeler le LLM
        if is_no_reply(msg.reply_to):
            print(f"\n=== {msg.email.subject} ===\nExpéditeur automatique (no-reply) : ignoré.")
            continue

        result = process_email(msg.email)
        print(f"\n=== {msg.email.subject} (de {msg.email.sender}) ===")
        print(f"Source: {result.source} | {result.category.value} | {result.priority.value}")
        print(f"Résumé: {result.summary}")

        if not result.reply_draft:
            print("Pas de brouillon généré (mode règles).")
            continue

        print(f"\n--- Brouillon proposé ---\n{result.reply_draft}\n")
        answer = input("Créer ce brouillon dans Gmail (rien ne sera envoyé) ? [o/N] ")
        if answer.strip().lower() == "o":
            try:
                draft_id = create_draft_reply(service, msg, result.reply_draft)
                print(f"Brouillon créé (id {draft_id}). Ouvre Gmail > Brouillons.")
            except GmailError as exc:
                print(f"Erreur: {exc}")
        else:
            print("Ignoré.")


if __name__ == "__main__":
    main()