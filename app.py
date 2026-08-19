"""AO-BTP Copilot Togo — interface Streamlit, style DeepSeek.

Un seul écran, un seul champ de saisie : l'utilisateur pose sa question et
reçoit sa réponse grounded sur le corpus légal togolais (Recueil ARCOP 2024).

Selon ce que demande l'utilisateur, l'app produit automatiquement :
    - un RÉSUMÉ d'un marché      (question contenant « résumé »)
    - une CHECKLIST d'éligibilité sourcée   (question contenant « checklist » / « éligibilité »)
    - sinon — une réponse Q&A grounded.

Moteur : **Ollama local uniquement** (`llama3.2:1b`). Aucun appel API externe.
L'index FAISS et le modèle d'embedding sont chargés une seule fois
(`@st.cache_resource`) ; chaque réponse est générée localement.

Lancement :  streamlit run app.py
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import llm_features as lf  # noqa: E402

CONSULTATIONS_DB = PROJECT_ROOT / "data" / "processed" / "consultations.db"

st.set_page_config(
    page_title="AO-BTP Copilot · Togo",
    page_icon=":material/construction:",
    layout="centered",
)


# ---------------------------------------------------------------------------
# Données + index (chargés une seule fois)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def charger_consultations() -> list[dict]:
    """Charge les avis d'appel d'offres réels depuis la base SQLite."""
    if not CONSULTATIONS_DB.exists():
        return []
    conn = sqlite3.connect(CONSULTATIONS_DB)
    conn.row_factory = sqlite3.Row
    lignes = [dict(r) for r in conn.execute(
        "SELECT * FROM consultations ORDER BY date_limite DESC")]
    conn.close()
    return lignes


@st.cache_resource(show_spinner=False)
def charger_index():
    """Charge l'index FAISS + le modèle d'embedding une seule fois par session."""
    from embeddings import creer_embedder
    from index_rag import IndexRAG, resoudre_backend

    backend = resoudre_backend(lf.FAISS_DIR)
    return IndexRAG.charger(lf.FAISS_DIR, creer_embedder(backend))


PROVIDER = "ollama"  # uniquement le modèle local d'Ollama
consultations = [a for a in charger_consultations()
                 if a.get("titre") or a.get("reference")]


def marche_par_ref(ref: str):
    return next((a for a in consultations if a["reference"] == ref), None)


def _repondre(question: str, ao, historique) -> str:
    """Aiguille la question vers résumé / checklist / Q&A grounded (Ollama local)."""
    q = (question or "").lower()
    if any(m in q for m in ("résumé", "resume", "récapitulatif")):
        if not ao:
            return ("Veuillez d'abord choisir un marché dans la barre latérale pour "
                    "que j'en fasse le résumé (objet, points clés, dispositions "
                    "applicables, articles du corpus).")
        return lf.resumer_ao(ao, provider=PROVIDER, index=charger_index())
    if any(m in q for m in ("checklist", "liste de vérification", "éligibilité",
                            "eligibilite", "conditions pour participer",
                            "puis-je soumissionner", "puis-je participer")):
        if not ao:
            return ("Veuillez d'abord choisir un marché dans la barre latérale pour "
                    "que j'établisse la checklist d'éligibilité (points à vérifier + "
                    "article du corpus).")
        return lf.checklist_eligibilite(ao, provider=PROVIDER, index=charger_index())
    return lf.repondre_question(question, historique=historique, ao=ao,
                                provider=PROVIDER, index=charger_index())


# ---------------------------------------------------------------------------
# Barre latérale (minimale)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("AO-BTP Copilot")
    st.caption("Marchés publics BTP · Togo\nRAG local — Recueil ARCOP 2024")
    st.markdown("---")
    if st.button(":material/chat: Nouvelle discussion"):
        st.session_state.messages = []
        st.rerun()

    refs = ["general"] + [a["reference"] for a in consultations]
    libelles = {
        "general": "Question générale (corpus entier)",
        **{a["reference"]: f"{a['reference']} — {(a['titre'] or '')[:55]}"
           for a in consultations},
    }
    sel = st.selectbox("Marché concerné", refs, format_func=lambda r: libelles[r])
    ao = None if sel == "general" else marche_par_ref(sel)
    st.caption("Moteur : **Ollama local** (llama3.2:1b)")
    st.caption("Réponses basées uniquement sur le corpus légal togolais.")
    if consultations:
        btp = sum(1 for a in consultations if a.get("is_btp"))
        st.caption(f"{len(consultations)} marchés recensés, {btp} BTP/Travaux.")


# ---------------------------------------------------------------------------
# Conversation (style DeepSeek : un chat, un champ de saisie)
# ---------------------------------------------------------------------------

st.header("AO-BTP Copilot")
st.caption("Posez votre question. Demandez un **résumé**, une **checklist "
           "d'éligibilité**, ou simplement une réponse ancrée sur le corpus "
           "juridique togolais.")

if ao:
    with st.container(border=True):
        st.markdown(f"**{ao['reference']}** — {ao['titre']}")
        st.caption(f"Type : {ao.get('type_marche') or '—'} · Statut : "
                   f"{ao.get('statut') or '—'} · Date limite : {ao.get('date_limite') or '—'}")
elif sel == "general":
    st.info("Mode **général** : réponses sur l'ensemble du corpus ARCOP 2024 "
            "(seuils, garanties, procédures, conditions de participation…).")

if "messages" not in st.session_state:
    st.session_state.messages = []

SHORT_PREFIX = ("Si votre question contient « résumé » ou « checklist », j'adapte "
                "automatiquement ma réponse.")


def _suggestion_btn(texte: str, i: int) -> None:
    if st.button(texte, key=f"sugg_{i}", use_container_width=True):
        st.session_state.question = texte
        st.rerun()


# Suggestions au démarrage (disparaissent dès le premier message)
if not st.session_state.messages:
    st.caption("Suggestions (cliquez pour poser la question) :")
    suggestions = [
        "Quels sont les seuils de passation des marchés de travaux au Togo ?",
        "Quelles garanties sont exigées pour les marchés de travaux ?",
    ]
    if ao:
        suggestions += [
            f"Résumé de ce marché ({sel})",
            f"Checklist d'éligibilité pour ce marché ({sel})",
        ]
    for i, texte in enumerate(suggestions):
        _suggestion_btn(texte, i)

# Saisie — TOUJOURS instanciée à chaque rerun : si chat_input n'est pas recréé
# (ex. quand une suggestion est en attente), le champ se désactive et la
# discussion ne peut plus continuer. Les suggestions passent par session_state,
# priorité à la saisie directe.
_prompt = st.chat_input(
    "Posez votre question (ex. « résumé du marché… », « checklist … », ou une question)",
    submit_mode="disable",
)
question = _prompt or st.session_state.pop("question", None)

if question:
    st.session_state.messages.append({"role": "user", "content": question})

# Rendu de l'historique (y compris le nouveau message utilisateur)
for m in st.session_state.messages:
    with st.chat_message(m["role"],
                         avatar=":material/person:" if m["role"] == "user"
                         else ":material/robot:"):
        st.markdown(m["content"])

# Génération de la réponse assistant si le dernier message n'a pas de suite
if question:
    # mémoire de conversation bornée (6 derniers tours) : les discussions
    # longues restent rapides et focalisées sur le contexte
    historique = [ {**m} for m in st.session_state.messages[-7:-1] ][-6:]
    with st.chat_message("assistant", avatar=":material/robot:"):
        t0 = time.perf_counter()
        try:
            with st.spinner("Lecture du corpus juridique…"):
                rep = _repondre(question, ao, historique)
            duree = time.perf_counter() - t0
            st.caption(f"Réponse en {duree:.0f} s · Ollama local · corpus ARCOP 2024")
            st.markdown(rep)
            for avertissement in lf.verifier_references(rep):
                st.warning(avertissement)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Impossible d'obtenir une réponse : {exc}")
            st.info("Vérifiez que le serveur Ollama tourne (`ollama serve`) et que "
                    "le modèle `llama3.2:1b` est installé (`ollama pull llama3.2:1b`).")
            rep = ""
    if rep:
        st.session_state.messages.append({"role": "assistant", "content": rep})