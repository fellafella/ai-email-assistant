"""Interface Streamlit : analyser un e-mail (collé ou venant de Gmail), éditer le
brouillon, l'approuver, puis l'enregistrer comme BROUILLON Gmail.

Aucun e-mail n'est envoyé par cette application.
"""
import logging

import streamlit as st

from gmail_client import GmailError, create_draft_reply, fetch_unread, get_service, skip_reason
from llm_assistant import process_email
from models import EmailInput, Priority

logger = logging.getLogger(__name__)
st.set_page_config(page_title="AI Email Assistant", page_icon="✉️")

# --- État initial -----------------------------------------------------------
DEFAULTS = {
    "sender": "", "subject": "", "body": "",
    "result": None, "draft": "", "approved": False, "reviewed": False,
    "error": None, "notice": None,
    "gmail_service": None, "inbox": [], "inbox_loaded": False,
    "gmail_msg": None, "draft_id": None,
}
for key, default in DEFAULTS.items():
    st.session_state.setdefault(key, default)


# --- Callbacks (exécutés AVANT le rechargement de la page) -------------------
def reset_outcome() -> None:
    """Efface le résultat précédent (nouvelle analyse ou nouvel e-mail)."""
    st.session_state.result = None
    st.session_state.draft = ""
    st.session_state.approved = False
    st.session_state.reviewed = False
    st.session_state.error = None
    st.session_state.notice = None
    st.session_state.draft_id = None


def load_inbox() -> None:
    reset_outcome()
    try:
        if st.session_state.gmail_service is None:
            st.session_state.gmail_service = get_service()  # ouvre le navigateur la 1re fois
        st.session_state.inbox = fetch_unread(st.session_state.gmail_service, max_results=10)
        st.session_state.inbox_loaded = True
        st.session_state.picked = None
    except Exception as exc:  # frontière de l'interface : on affiche l'erreur
        logger.exception("Connexion Gmail impossible")
        st.session_state.error = f"Connexion Gmail impossible : {exc}"


def pick_message() -> None:
    index = st.session_state.get("picked")
    if index is None:
        return
    msg = st.session_state.inbox[index]
    reset_outcome()
    st.session_state.gmail_msg = msg
    st.session_state.sender = msg.email.sender or ""
    st.session_state.subject = msg.email.subject
    st.session_state.body = msg.email.body


def detach_gmail_message() -> None:
    """Si l'utilisateur modifie l'e-mail à la main, on ne l'associe plus au fil Gmail."""
    st.session_state.gmail_msg = None


def analyze() -> None:
    reset_outcome()
    if not st.session_state.body.strip():
        st.session_state.error = "Le corps de l'e-mail est vide."
        return
    msg = st.session_state.gmail_msg
    reason = skip_reason(msg) if msg else None
    if reason:
        st.session_state.notice = f"Pas de réponse proposée : {reason}."
        return
    email = EmailInput(
        sender=st.session_state.sender or None,
        subject=st.session_state.subject,
        body=st.session_state.body,
    )
    result = process_email(email)
    st.session_state.result = result
    st.session_state.draft = result.reply_draft


def reset_approval() -> None:
    """Si le brouillon est modifié, l'approbation précédente n'est plus valable."""
    st.session_state.approved = False
    st.session_state.draft_id = None


def approve() -> None:
    st.session_state.approved = True


def save_gmail_draft() -> None:
    try:
        st.session_state.draft_id = create_draft_reply(
            st.session_state.gmail_service, st.session_state.gmail_msg, st.session_state.draft
        )
    except GmailError as exc:
        st.session_state.error = str(exc)


# --- Barre latérale : Gmail --------------------------------------------------
with st.sidebar:
    st.header("Gmail")
    st.caption("Lecture seule + création de brouillons. Jamais d'envoi.")
    st.button("Charger mes e-mails non lus", key="load_btn", on_click=load_inbox)
    if st.session_state.inbox:
        inbox = st.session_state.inbox
        st.selectbox(
            "Choisis un e-mail",
            options=list(range(len(inbox))),
            index=None,
            placeholder="Sélectionne un e-mail",
            format_func=lambda i: (
                ("(auto) " if skip_reason(inbox[i]) else "") + (inbox[i].email.subject or "(sans objet)")[:50]
            ),
            key="picked",
            on_change=pick_message,
        )
    elif st.session_state.inbox_loaded:
        st.caption("Aucun e-mail non lu.")

# --- Page principale ---------------------------------------------------------
st.title("✉️ AI Email Assistant")
st.caption("Colle un e-mail (ou charge-le depuis Gmail), vérifie l'analyse, modifie le "
           "brouillon puis approuve-le. Rien n'est envoyé automatiquement.")

st.text_input("Expéditeur (optionnel)", key="sender", on_change=detach_gmail_message)
st.text_input("Objet", key="subject", on_change=detach_gmail_message)
st.text_area("Contenu de l'e-mail", key="body", height=180, on_change=detach_gmail_message)
if st.session_state.gmail_msg:
    st.caption("📬 E-mail chargé depuis Gmail : le brouillon pourra être enregistré dans le même fil.")
st.button("Analyser", type="primary", key="analyze_btn", on_click=analyze)

if st.session_state.error:
    st.error(st.session_state.error)
if st.session_state.notice:
    st.info(st.session_state.notice)

result = st.session_state.result
if result:
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("Catégorie", result.category.value)
    col2.metric("Priorité", result.priority.value)
    if result.priority == Priority.HIGH:
        st.warning("Priorité haute : cet e-mail demande une attention rapide.")

    st.write(f"**Résumé :** {result.summary}")
    if result.source == "rules":
        st.info("Mode règles : le LLM est indisponible, donc aucun brouillon n'a été "
                "généré. Tu peux écrire ta réponse ci-dessous.")

    st.subheader("Brouillon de réponse")
    st.text_area("Modifie le brouillon si nécessaire", key="draft", height=250,
                 on_change=reset_approval)

    st.checkbox("J'ai relu ce brouillon et je le valide", key="reviewed")
    st.button("Approuver le brouillon", key="approve_btn", on_click=approve,
              disabled=not (st.session_state.reviewed and st.session_state.draft.strip()))

    if st.session_state.approved:
        if st.session_state.gmail_msg and st.session_state.gmail_service:
            st.button("Enregistrer comme brouillon Gmail", key="save_btn",
                      on_click=save_gmail_draft)
            if st.session_state.draft_id:
                st.success("Brouillon enregistré dans Gmail (dossier Brouillons). "
                           "Rien n'a été envoyé : relis-le et envoie-le toi-même.")
        else:
            st.success("Brouillon approuvé. Copie-le avec le bouton ci-dessous : "
                       "l'application n'envoie aucun e-mail.")
            st.code(st.session_state.draft, language=None)