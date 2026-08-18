"""Features LLM grounded sur le RAG — résumé, checklist d'éligibilité, chat Q&A.

Chaque feature récupère le contexte juridique pertinent via l'index FAISS
(`data/processed/faiss`) puis appelle un modèle de génération avec un prompt
grounded : le modèle doit répondre UNIQUEMENT à partir du contexte fourni, en
citant les articles (ex. « Article 12 »).

Modèle par défaut : **Groq openai/gpt-oss-120b** (gratuit, citations fiables —
verdict du benchmark réel) ; **Ollama llama3.2:1b** en repli local (hors-ligne)
via `provider="ollama"` (cite moins bien, plus lent). Voir
`src/llm_benchmark.py` pour le catalogue et la couche d'appels (`call_model`).

Design : les fonctions de *prompt* et de *mise en forme* sont pures et testables
sans réseau ; la génération est **injectable** (`generer`=callable, en défaut
`call_model`) pour les tests. Rien ne fait d'appel réseau à l'import.

Fonctions publiques :
    resumer_ao(ao, ...)                → résumé structuré de l'AO + points légaux
    checklist_eligibilite(ao, ...)     → checklist d'éligibilité sourcée
    repondre_question(q, historique)   → chat Q&A grounded (anti-hallucination)
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAISS_DIR = PROJECT_ROOT / "data" / "processed" / "faiss"
# groq : gratuit + citations fiables (benchmark réel) ; ollama : repli hors-ligne.
PROVIDER_DEFAUT = "groq"


# ---------------------------------------------------------------------------
# RAG : récupération du contexte juridique
# ---------------------------------------------------------------------------

def rechercher(question: str, k: int = 6, repertoire: Path = FAISS_DIR) -> list[dict]:
    """Retourne les k chunks les plus proches de `question` (index FAISS réel).

    Le backend d'embedding suit `config.json` (local par défaut). L'index et
    l'embedder sont chargés à la demande : pas de coût à l'import.
    """
    from embeddings import creer_embedder
    from index_rag import IndexRAG, resoudre_backend

    backend = resoudre_backend(repertoire)
    embedder = creer_embedder(backend)
    index = IndexRAG.charger(repertoire, embedder)
    return index.rechercher(question, k=k)


def formater_contexte(chunks: list[dict]) -> str:
    """Met les chunks récupérés en contexte lisible pour le modèle (avec source)."""
    if not chunks:
        return "(aucun extrait pertinent trouvé dans le corpus)"
    blocs = []
    for c in chunks:
        source = f"{c['document']}, Article {c['article']}"
        if c.get("titre"):
            source += f" — {c['titre']}"
        blocs.append(f"[{source}]\n{c['texte']}")
    return "\n\n---\n\n".join(blocs)


def texte_ao(ao: dict) -> str:
    """Représentation texte lisible des champs d'un AO (pour les prompts)."""
    lignes = []
    ordre = [
        ("reference", "Référence"),
        ("titre", "Titre"),
        ("objet", "Objet"),
        ("entite", "Entité contractante"),
        ("type_marche", "Type de marché"),
        ("statut", "Statut"),
        ("date_limite", "Date limite"),
        ("montant_previsionnel", "Montant prévisionnel"),
        ("garantie_soumission", "Garantie de soumission"),
        ("delai_execution", "Délai d'exécution"),
        ("validite_offres", "Validité des offres"),
        ("lieu_depot", "Lieu de dépôt"),
        ("contact_consultation", "Contact"),
    ]
    for cle, label in ordre:
        val = ao.get(cle)
        if val:
            lignes.append(f"- {label} : {val}")
    if not lignes:
        lignes.append("- (aucun champ renseigné)")
    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Prompts grounded (système + utilisateur)
# ---------------------------------------------------------------------------

def _system_grounded(consigne: str) -> str:
    return (
        "Tu es un assistant spécialisé en marchés publics et commande publique au "
        "Togo, pour une PME du BTP. Tu réponds UNIQUEMENT à partir du CONTEXTE "
        "fourni (extraits juridiques et fiche de l'appel d'offres). Si une "
        "information n'est pas dans le contexte, dis-le explicitement, n'invente "
        "rien. Cite les articles lorsque tu t'appuies sur eux (ex. « Article 12 »).\n\n"
        + consigne
    )


def prompt_resume(ao: dict, contexte: str) -> tuple[str, str]:
    """Prompt du résumé : points clés de l'AO + dispositions applicables."""
    system = _system_grounded(
        "Rédige un résumé SYNTHÉTIQUE d'un appel d'offres pour un entrepreneur du "
        "BTP : en quelques lignes, l'objet et les faits clés de la fiche AO, puis "
        "une section « Dispositions applicables » listant, avec leur article, les "
        "points du corpus légal pertinents pour ce marché (procédure, seuils, "
        "garanties, capacités). Si un aspect ne figure pas dans le contexte, "
        "signale son absence plutôt que de supposer."
    )
    user = (
        "FICHE DE L'APPEL D'OFFRES :\n"
        f"{texte_ao(ao)}\n\n"
        "CONTEXTE JURIDIQUE (extraits du corpus de la commande publique du Togo) :\n"
        f"{contexte}"
    )
    return system, user


def prompt_checklist(ao: dict, contexte: str) -> tuple[str, str]:
    """Prompt de la checklist d'éligibilité sourcée (avec citation d'article)."""
    system = _system_grounded(
        "Établis une CHECKLIST d'éligibilité pour l'entreprise candidate, à partir "
        "des conditions du contexte : liste de points à vérifier, chacun complété "
        "par la règle applicable et son article (ex. « Article 27 »). Pour chaque "
        "point : « À vérifier », « Règle », « Référence ». Termine par un bloc "
        "« Non couvert par le corpus » pour toute condition qui ne figure pas dans "
        "le contexte."
    )
    user = (
        "FICHE DE L'APPEL D'OFFRES :\n"
        f"{texte_ao(ao)}\n\n"
        "CONTEXTE JURIDIQUE (extraits du corpus de la commande publique du Togo) :\n"
        f"{contexte}"
    )
    return system, user


def prompt_chat(question: str, historique: list[dict], contexte: str) -> tuple[str, str]:
    """Prompt du chat Q&A grounded, avec historique limité pour rester focalisé."""
    system = _system_grounded(
        "Réponds à la question de l'utilisateur à partir du CONTEXTE fourni "
        "(extraits juridiques) et, le cas échéant, de la fiche de l'AO. Cites "
        "les articles précis dont tu t'appuies. Si l'information manque, réponds "
        "honnêtement que le corpus ne la contient pas."
    )
    historique_txt = "\n".join(
        f"{'Utilisateur' if m.get('role') == 'user' else 'Assistant'} : {m['content']}"
        for m in (historique or [])
    )
    user = (
        "CONTEXTE JURIDIQUE (extraits du corpus de la commande publique du Togo) :\n"
        f"{contexte}\n\n"
        + (f"ÉCHANGES PRÉCÉDENTS :\n{historique_txt}\n\n" if historique_txt else "")
        + f"Question : {question}"
    )
    return system, user


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def _generer(provider: str, system: str, user: str, generer=None,
             max_output_tokens: int = 1000) -> str:
    """Passe le prompt au modèle ; `generer` injectable (défaut call_model).

    La borne de sortie doit être assez haute pour les modèles « à raisonnement »
    (gpt-oss-120b consomme une partie des tokens en raisonnement avant la réponse) :
    une borne trop basse → réponse tronquée/vide (constaté avec max=500).
    """
    if generer is None:
        from llm_benchmark import call_model

        res = call_model(provider, system, user, max_output_tokens=max_output_tokens)
        if not res["ok"]:
            raise RuntimeError(f"Échec d'appel {provider} : {res['erreur']}")
        text = (res["text"] or "").strip()
    else:
        text = str(generer(provider, system, user) or "").strip()
    if not text:
        raise RuntimeError(
            f"Réponse vide de {provider} (tokens consommés = oui, texte = non). "
            "Signe souvent d'une borne max_output_tokens trop basse pour un "
            "modèle à raisonnement — augmentez-la."
        )
    return text


def _contexte_requetes(focus: str, k: int) -> str:
    """Récupère le contexte RAG autour de `focus` et le met en forme."""
    return formater_contexte(rechercher(focus, k=k))


def resumer_ao(ao: dict, k: int = 6, provider: str = PROVIDER_DEFAUT,
               focus: str | None = None, generer=None,
               max_output_tokens: int = 1000) -> str:
    """Résumé grounded d'un AO : objet + dispositions applicables sourcées."""
    focus = focus or f"{ao.get('titre', '') or ''} {ao.get('objet', '') or ''}".strip()
    contexte = _contexte_requetes(focus or "appel d'offres travaux", k)
    system, user = prompt_resume(ao, contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)


def checklist_eligibilite(ao: dict, k: int = 8, provider: str = PROVIDER_DEFAUT,
                          focus: str | None = None, generer=None,
                          max_output_tokens: int = 1000) -> str:
    """Checklist d'éligibilité sourcée (citation d'article à chaque point)."""
    focus = focus or f"{ao.get('titre', '') or ''} {ao.get('objet', '') or ''} "
    focus = (focus + "conditions de participation capacités garanties").strip()
    contexte = _contexte_requetes(focus, k)
    system, user = prompt_checklist(ao, contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)


def repondre_question(question: str, historique: list[dict] | None = None,
                      ao: dict | None = None, k: int = 5,
                      provider: str = PROVIDER_DEFAUT, generer=None,
                      max_output_tokens: int = 1000) -> str:
    """Répond à une question avec contexte RAG + fiche AO + historique."""
    ao = ao or {}
    focus = f"{question} {ao.get('titre', '') or ''} {ao.get('objet', '') or ''}".strip()
    contexte = _contexte_requetes(focus, k)
    if ao:
        contexte = f"FICHE DE L'APPEL D'OFFRES :\n{texte_ao(ao)}\n\n" + contexte
    system, user = prompt_chat(question, historique or [], contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)