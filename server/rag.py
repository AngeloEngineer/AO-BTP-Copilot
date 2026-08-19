"""Couche RAG du serveur — récupération + génération avec streaming Ollama.

Réutilise le moteur de `src/llm_features.py` (prompts grounded, index FAISS,
aiguillage résumé/checklist/chat) et ajoute une génération **streamée** via le
client Ollama (un message multi-utilisateurs ne doit pas attendre 2 minutes
sans retour visuel). L'index FAISS est chargé une seule fois par processus.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import llm_features as lf  # noqa: E402
from llm_benchmark import MODELS_CATALOG  # noqa: E402

from .config import (  # noqa: E402
    CONSULTATIONS_DB,
    HISTORIQUE_MAX_TOURS,
    MAX_OUTPUT_TOKENS,
    OLLAMA_HOST,
    OLLAMA_MODELE,
)

_index: object | None = None
_consultations: list[dict] | None = None


def charger_index():
    """Index FAISS global (chargé une fois par processus)."""
    global _index
    if _index is None:
        from embeddings import creer_embedder
        from index_rag import IndexRAG, resoudre_backend

        backend = resoudre_backend(lf.FAISS_DIR)
        _index = IndexRAG.charger(lf.FAISS_DIR, creer_embedder(backend))
    return _index


def charger_consultations() -> list[dict]:
    """Avis d'appel d'offres réels (cache d'une requête SQLite)."""
    global _consultations
    if _consultations is None:
        if not CONSULTATIONS_DB.exists():
            _consultations = []
        else:
            conn = sqlite3.connect(CONSULTATIONS_DB)
            conn.row_factory = sqlite3.Row
            _consultations = [dict(r) for r in conn.execute(
                "SELECT * FROM consultations ORDER BY date_limite DESC")]
            conn.close()
    return _consultations


def marche_par_ref(ref: str) -> dict | None:
    return next((a for a in charger_consultations() if a["reference"] == ref), None)


def _texte_introduction_sans_marche(intention: str) -> str:
    if intention == "resume":
        return ("Veuillez d'abord sélectionner un marché dans la barre latérale "
                "pour que j'en fasse le résumé (objet, points clés, dispositions "
                "applicables) avec les articles du corpus.")
    if intention == "checklist":
        return ("Veuillez d'abord sélectionner un marché dans la barre latérale pour "
                "que j'établisse la checklist d'éligibilité (points à vérifier + "
                "article du corpus).")
    return ""


def construire_prompt(message: str, marche: str | None, historique: list[dict]) -> dict:
    """Prépare l'appel modèle : aiguillage + prompts grounded (retrieval compris).

    Retourne {"intention": str, "ao": dict|None, "system": str, "user": str}
    sans faire d'appel réseau de génération (l'index seul est sollicité).
    """
    intention = lf.intention(message)
    ao = (None if marche in (None, "", "general") else marche_par_ref(marche)) or None
    ao_dict = ao or {}
    index = charger_index()

    if intention != "chat" and ao is None:
        # le modèle n'a pas de fiche sur laquelle travailler : message d'attente
        texte = _texte_introduction_sans_marche(intention)
        return {"intention": intention, "ao": None,
                "system": "...", "user": "...", "introduction": texte}

    if intention == "resume":
        focus = f"{ao.get('titre', '')} {ao.get('objet', '')}".strip() or "appel d'offres travaux"
        contexte = lf._contexte_requetes(focus, 6, index=index)
        system, user = lf.prompt_resume(ao, contexte)
    elif intention == "checklist":
        focus = f"{ao.get('titre', '')} {ao.get('objet', '')} "
        focus = (focus + "conditions de participation capacités garanties").strip()
        contexte = lf._contexte_requetes(focus, 8, index=index)
        system, user = lf.prompt_checklist(ao, contexte)
    else:
        focus = f"{message} {ao_dict.get('titre', '')} {ao_dict.get('objet', '')}".strip()
        contexte = lf._contexte_requetes(focus, 5, index=index)
        if ao:
            contexte = f"FICHE DE L'APPEL D'OFFRES :\n{lf.texte_ao(ao)}\n\n" + contexte
        system, user = lf.prompt_chat(message, historique or [], contexte)

    return {"intention": intention, "ao": ao, "system": system, "user": user,
            "introduction": ""}


def generer_ollama_stream(system: str, user: str):
    """Générateur : flux de fragments de texte depuis Ollama local (streaming)."""
    if system == "...":
        return iter(())  # cas introduction : aucun appel modèle
    from ollama import Client

    client = Client(host=OLLAMA_HOST)
    stream = client.chat(
        model=MODELS_CATALOG.get("ollama", {}).get("modele", OLLAMA_MODELE),
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        options={"num_predict": MAX_OUTPUT_TOKENS},
        stream=True,
    )
    for partie in stream:
        fragment = (partie.get("message") or {}).get("content") or ""
        if fragment:
            yield fragment


def historique_recent(messages: list[dict]) -> list[dict]:
    """Derniers messages (rôle+contenu) avant la nouvelle question, borné."""
    return [{"role": m["role"], "content": m["content"]}
            for m in messages[-HISTORIQUE_MAX_TOURS:]]