"""Features LLM grounded sur le RAG — résumé, checklist d'éligibilité, chat Q&A.

Chaque feature récupère le contexte juridique pertinent via l'index FAISS
(`data/processed/faiss`) puis appelle un modèle de génération avec un prompt
grounded : le modèle doit répondre UNIQUEMENT à partir du contexte fourni, en
citant les articles (ex. « Article 12 »).

Modèle par défaut : **Ollama local `llama3.2:1b`** (décision produit du 18/08/2026 —
interface locale uniquement) ; Groq openai/gpt-oss-120b reste disponible dans le code
pour comparaison en benchmark. Un modèle 1B invente parfois des références :
`verifier_references()` (post-traitement, 100 % local) signale toute citation
introuvable dans le corpus ARCOP 2024. Voir `src/llm_benchmark.py` pour le catalogue.

Design : les fonctions de *prompt* et de *mise en forme* sont pures et testables
sans réseau ; la génération est **injectable** (`generer`=callable, en défaut
`call_model`) pour les tests. Rien ne fait d'appel réseau à l'import.

Fonctions publiques :
    resumer_ao(ao, ...)                → résumé structuré de l'AO + points légaux
    checklist_eligibilite(ao, ...)     → checklist d'éligibilité sourcée
    repondre_question(q, historique)   → chat Q&A grounded (anti-hallucination)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAISS_DIR = PROJECT_ROOT / "data" / "processed" / "faiss"
# groq : gratuit + citations fiables (benchmark réel) ; ollama : repli hors-ligne.
PROVIDER_DEFAUT = "ollama"


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


def rechercher_index(index, question: str, k: int = 6) -> list[dict]:
    """Variante sur un index déjà chargé (évite de recharger le modèle d'embedding)."""
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
        "rien. N'invente JAMAIS un décret, une loi, un arrêté, un article, un "
        "montant, un organisme, un contact ou une URL : seule une référence "
        "présente dans le CONTEXTE peut être citée, telle quelle. Cite les "
        "articles lorsque tu t'appuies sur eux (ex. « Article 12 »).\n\n"
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


def intention(question: str | None) -> str:
    """Aiguille une question vers 'resume', 'checklist' ou 'chat' (défaut)."""
    q = (question or "").lower()
    if any(m in q for m in ("résumé", "resume", "récapitulatif")):
        return "resume"
    if any(m in q for m in ("checklist", "liste de vérification", "éligibilité",
                            "eligibilite", "conditions pour participer",
                            "puis-je soumissionner", "puis-je participer")):
        return "checklist"
    return "chat"


def _contexte_requetes(focus: str, k: int, index=None) -> str:
    """Récupère le contexte RAG autour de `focus` et le met en forme.

    `index` optionnel : un index FAISS déjà chargé (pour éviter de recharger le
    modèle d'embedding à chaque appel — utile côté interface) ; sinon chargement
    à la demande via `rechercher`.
    """
    if index is not None:
        chunks = index.rechercher(focus, k=k)
    else:
        chunks = rechercher(focus, k=k)
    return formater_contexte(chunks)


def resumer_ao(ao: dict, k: int = 6, provider: str = PROVIDER_DEFAUT,
               focus: str | None = None, generer=None, index=None,
               max_output_tokens: int = 1000) -> str:
    """Résumé grounded d'un AO : objet + dispositions applicables sourcées."""
    focus = focus or f"{ao.get('titre', '') or ''} {ao.get('objet', '') or ''}".strip()
    contexte = _contexte_requetes(focus or "appel d'offres travaux", k, index=index)
    system, user = prompt_resume(ao, contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)


def checklist_eligibilite(ao: dict, k: int = 8, provider: str = PROVIDER_DEFAUT,
                          focus: str | None = None, generer=None, index=None,
                          max_output_tokens: int = 1000) -> str:
    """Checklist d'éligibilité sourcée (citation d'article à chaque point)."""
    focus = focus or f"{ao.get('titre', '') or ''} {ao.get('objet', '') or ''} "
    focus = (focus + "conditions de participation capacités garanties").strip()
    contexte = _contexte_requetes(focus, k, index=index)
    system, user = prompt_checklist(ao, contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)


def repondre_question(question: str, historique: list[dict] | None = None,
                      ao: dict | None = None, k: int = 5,
                      provider: str = PROVIDER_DEFAUT, generer=None, index=None,
                      max_output_tokens: int = 1000) -> str:
    """Répond à une question avec contexte RAG + fiche AO + historique."""
    ao = ao or {}
    focus = f"{question} {ao.get('titre', '') or ''} {ao.get('objet', '') or ''}".strip()
    contexte = _contexte_requetes(focus, k, index=index)
    if ao:
        contexte = f"FICHE DE L'APPEL D'OFFRES :\n{texte_ao(ao)}\n\n" + contexte
    system, user = prompt_chat(question, historique or [], contexte)
    return _generer(provider, system, user, generer,
                    max_output_tokens=max_output_tokens)


# ---------------------------------------------------------------------------
# Vérification des références (garde-fou anti-hallucination, 100 % local)
# ---------------------------------------------------------------------------

_DOC_RE = re.compile(
    r"\b(d[ée]cret|loi|arr[êe]t[ée]|directive)\s*(?:n[°ºo]?\s*\.?\s*)?"
    r"(\d{3,4}-\d{2,4}|\d{1,4}(?:[-/]\d{1,4})?)",
    re.IGNORECASE,
)
_ART_RE = re.compile(r"\barticle\s+(premier|1er|1\b|\d+)\b", re.IGNORECASE)


def _ancrer_repertoire_corpus(repertoire: Path = FAISS_DIR) -> tuple[set[str], set[str]]:
    """N° de textes et n° d'articles réellement présents dans le corpus (meta FAISS)."""
    meta_path = Path(repertoire) / "meta.json"
    numeros_textes: set[str] = set()
    numeros_articles: set[str] = set()
    if not meta_path.exists():
        return numeros_textes, numeros_articles
    chunks = json.loads(meta_path.read_text(encoding="utf-8"))
    for c in chunks:
        numeros_articles.add(str(c.get("article", "")).strip().upper())
    for doc in sorted({c.get("document", "") for c in chunks if c.get("document")}):
        # "decret-2019-096-maitrise-ouvrage" → {2019-096, 2019-96, 96} ; "0178-171"…
        parts = [p for p in doc.split("-") if p.isdigit()]
        numeros_textes.add("-".join(parts))
        if "-".join(parts) not in ("01-2022", "087"):
            numeros_textes.add("-".join(parts[1:]) if len(parts) > 2 else "-".join(parts))
        if len(parts) >= 2:
            numeros_textes.add("-".join(parts[1:]))
        if parts:
            numeros_textes.add(str(int(parts[-1])))
    numeros_textes -= {"", "-"}
    return numeros_textes, numeros_articles


def verifier_references(texte: str, repertoire: Path = FAISS_DIR) -> list[str]:
    """Signale dans `texte` les références qui n'existent PAS dans le corpus.

    Détecte les mentions « décret / loi / arrêté / directive n° … » et « article
    N », puis les confronte aux textes et articles réellement présents dans le
    Recueil ARCOP 2024 (`meta.json` de l'index FAISS). Sert de garde-fou :
    un modèle 1B peut inventer des références (ex. « décret n° 2019-1010 ») —
    mieux vaut les signaler que les laisser croire exactes.
    """
    numeros_textes, numeros_articles = _ancrer_repertoire_corpus(repertoire)
    if not numeros_textes:
        return []
    avertissements: list[str] = []
    vus: set[str] = set()

    for m in _DOC_RE.finditer(texte):
        token = m.group(0)
        numero = re.sub(r"[^0-9-]", "", m.group(2))  # "2019-096" / "087" / "90-02"
        candidates = {numero}
        for part in numero.split("-"):
            candidates.add(part)
        if numero.startswith("0") and len(numero) > 1:
            candidates.add(numero.lstrip("0") or "0")
        if not (candidates & numeros_textes) and token.lower() not in vus:
            vus.add(token.lower())
            avertissements.append(
                f"Référence douteuse : « {token} » est introuvable dans le "
                f"corpus ARCOP 2024 (vérifier avant toute utilisation)."
            )

    for m in _ART_RE.finditer(texte):
        numero = {"premier": "1", "1er": "1", "1": "1"}.get(m.group(1), m.group(1))
        if numero not in numeros_articles and m.group(1).upper() not in numeros_articles:
            avertissements.append(
                f"Référence douteuse : « Article {numero} » n'existe pas dans "
                f"le corpus ARCOP 2024 (vérifier avant toute utilisation)."
            )
    return avertissements