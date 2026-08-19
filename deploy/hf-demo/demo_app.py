"""Démo portfolio du RAG AO-BTP Copilot (Hugging Face Spaces, Docker).

Expose le moteur RAG de `server/rag.py` (retrieval FAISS local + génération
Ollama `llama3.2:1b` en streaming) SANS aucune authentification : quiconque
possède l'URL peut poser une question. Interface Gradio.
"""

from __future__ import annotations

import os

import gradio as gr

from server import rag


def choix_marches() -> list[tuple[str, str]]:
    try:
        consultations = rag.charger_consultations()
    except Exception:
        consultations = []
    choix = [("general", "Aucun - discussion générale sur le corpus")]
    for a in consultations:
        titre = (a.get("titre") or "") or (a.get("objet") or "")
        label = f"{a['reference']}  |  {titre[:70]}"
        choix.append((a["reference"], label))
    return choix


def repondre(message: str, history, marches: str):
    historique = []
    for tour in (history or [])[-6:]:
        if isinstance(tour, dict) and "role" in tour:
            historique.append({"role": tour.get("role", "user"),
                               "content": tour.get("content", "") or ""})
        elif len(tour) >= 2:
            historique.append({"role": "user", "content": tour[0] or ""})
            historique.append({"role": "assistant", "content": tour[1] or ""})
    historique = rag.historique_recent(historique)

    try:
        prep = rag.construire_prompt(message, marches, historique)
    except Exception as exc:
        yield f"Impossible de préparer la recherche dans le corpus : {exc}"
        return

    if prep.get("introduction"):
        yield prep["introduction"]
        return

    acc = ""
    try:
        for fragment in rag.generer_ollama_stream(prep["system"], prep["user"]):
            acc += fragment
            yield acc
    except Exception as exc:
        if not acc:
            acc = ("Le modèle local n'a pas répondu (démarrage à froid ?). "
                   f"Réessaie dans quelques secondes. ({exc})")
        else:
            acc += f"\n\n_(génération interrompue : {exc})_"
        yield acc


def main() -> None:
    choix = choix_marches()
    valeur_defaut = choix[0][0] if choix else "general"

    with gr.Blocks(title="AO-BTP Copilot - démo RAG", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# AO-BTP Copilot - démo RAG\n"
            "Teste en direct l'assistant RAG construit pour suivre les appels "
            "d'offres de marchés publics (corpus juridique + avis d'appel "
            "d'offres). Réponses en streaming par un modèle local "
            "(`llama3.2:1b` - Ollama), sources extraites de l'index FAISS.\n"
            "\n"
            "Aucun compte requis : pose une question directement."
        )
        marches = gr.Dropdown(
            choices=choix,
            value=valeur_defaut,
            label=("Appel d'offres (optionnel) - sert pour les résumés et "
                   "checklists d'éligibilité"),
        )
        gr.ChatInterface(
            fn=repondre,
            additional_inputs=[marches],
            examples=[
                "Quelles sont les conditions de participation à un marché de travaux ?",
                "Que doit contenir le dossier de candidature ?",
                "Citer les règles sur les garanties et les avances de démarrage.",
                "Comment se déroule l'évaluation des offres ?",
                "Quelle durée de validité des offres est généralement exigée ?",
            ],
        )
        gr.Markdown(
            "(Démo technique : modèle local 1B, réponses à vérifier sur les "
            "sources officielles. Le premier message après une période "
            "d'inactivité peut prendre 30 à 60 s.)"
        )

    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", "7860")),
        show_error=True,
    )


if __name__ == "__main__":
    main()