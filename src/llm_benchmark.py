"""Noyau du benchmark LLM — AO-BTP Copilot.

But : challenger les modèles candidats (Gemini 3.5 Flash, Groq openai/gpt-oss-120b,
Ollama local, etc.) sur 7 critères clés, à partir d'un jeu d'évaluation grounded
(questions ancrées sur le corpus légal réel) et, pour les critères qualitatifs,
d'un score attribué par un "juge LLM" (un autre modèle, si possible non concurrent)
complété d'un échantillon de vérification manuelle.

Ce module est importé par le notebook notebooks/benchmark_llm.ipynb. Il ne fait
AUCUN appel réseau : les clients sont construits à la demande ; toutes les
fonctions de scoring sont pures et testables sans clé API.

Les 7 critères (identifiants stables) :
    grounding        — fidélité au contexte (un contexte piégé doit être suivi)
    citations        — la citation exacte de l'article attendu apparaît dans la réponse
    langue           — qualité du français / clampage jargon marchés (juge LLM 0-5)
    latence          — temps de réponse mesuré (durée formatée)
    cout             — coût estimé par requête (tokens × grille tarifaire)
    quotas           — tenue sous limitations du fournisseur (RPM/RPD, jet gratuits)
    robustesse       — réussite de l'appel, format de sortie, réponses hors contexte
                      dans les cas "info absente" (honnêteté)
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
EVAL_PATH = DATA_DIR / "eval" / "eval_questions.json"
RESULTS_DIR = DATA_DIR / "processed"

# --- Chargement des clés (jamais affichées) --------------------------------
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Constantes "modèles testés" : libellés stables pour le notebook
# ---------------------------------------------------------------------------

# Chaque entrée : id, fournisseur, modèle, grille tarifaire (USD / 1M tokens,
# input/output), type d'accès.
MODELS_CATALOG: dict[str, dict] = {
    "gemini-3.5-flash": {
        "fournisseur": "gemini",
        "modele": "gemini-3.5-flash",
        "prix_in_par_million": 1.50,
        "prix_out_par_million": 9.00,
        "quota_rpm": 15,
        "quota_rpd": 20,
        "gratuit": True,
        "note": "Modèle choisi par l'utilisateur (première option). Vérifié le 16/08/2026. "
                "Quota free tier réel constaté le 17/08/2026 : 20 req/jour (429 RESOURCE_EXHAUSTED, "
                "quotaValue 20, par projet et par modèle, réinit à minuit Pacific) — variable selon compte.",
    },
    "groq-gpt-oss-120b": {
        "fournisseur": "groq",
        "modele": "openai/gpt-oss-120b",
        "prix_in_par_million": 0.0,  # gratuit
        "prix_out_par_million": 0.0,
        "quota_rpm": 30,
        "quota_rpd": 14400,
        "gratuit": True,
        "note": "Challenger Groq validé par l'utilisateur le 17/08/2026 (deepseek-r1-distill-70b "
                "retiré de Groq — 404 vérifié en réel). API compatible OpenAI.",
    },
    "ollama": {
        "fournisseur": "ollama",
        "modele": "llama3.2:1b",
        "prix_in_par_million": 0.0,  # local, gratuit
        "prix_out_par_million": 0.0,
        "gratuit": True,
        "note": "Modèle Ollama léger local retenu pour les features (J3). "
                "`qwen3.6:27b` retiré (disque) ; `llama3.2:1b` installé (1.3 GB). "
                "Qualité attendue limitée (1B) — à confirmer par le benchmark en réel.",
    },
}


# ---------------------------------------------------------------------------
# Clients fournisseurs — construits à la demande (pas de réseau à l'import)
# ---------------------------------------------------------------------------

def build_gemini_client():
    """Client Gemini à partir de la clé GEMINI_API_KEY."""
    from google import genai
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))


def build_groq_client():
    """Client Groq (API compatible OpenAI) à partir de la clé GROQ_API_KEY."""
    from openai import OpenAI
    return OpenAI(base_url="https://api.groq.com/openai/v1",
                  api_key=os.environ.get("GROQ_API_KEY", ""))


def build_ollama_client():
    """Client Ollama local (pas de clé). Ollama doit tourner sur le poste."""
    from ollama import Client
    return Client(host="http://localhost:11434")


# ---------------------------------------------------------------------------
# Appels synchrones aux modèles (chacun renvoie (texte, usage) ou None)
# ---------------------------------------------------------------------------

def call_model(provider_id: str, system: str, user: str,
               max_output_tokens: int = 1500,
               retry_429: int = 3, backoff_base: float = 8.0) -> dict:
    """Appelle le modèle désigné et retourne un dict normalisé.

    Retourne : {"text": str, "usage_in": int, "usage_out": int,
                "ok": bool, "erreur": str|None}
    Fait une retry limitée (retry_429, backoff exponentiel) quand le fournisseur
    renvoie un 429 (quota/réservation) : ces erreurs sont souvent transitoires
    (le quota se libère en quelques secondes à minutes). Les autres erreurs
    (auth, modèle absent…) ne sont pas retentées.
    """
    start = perf_counter()
    usage_in = usage_out = 0
    last_err = ""
    for essai in range(retry_429 + 1):
        try:
            if provider_id == "gemini":
                client = build_gemini_client()
                resp = client.models.generate_content(
                    model=MODELS_CATALOG["gemini-3.5-flash"]["modele"],
                    contents=user,
                    config={"system_instruction": system,
                            "max_output_tokens": max_output_tokens},
                )
                text = (resp.text or "").strip()
                if resp.usage_metadata:
                    usage_in = resp.usage_metadata.prompt_token_count or 0
                    usage_out = resp.usage_metadata.candidates_token_count or 0

            elif provider_id == "groq":
                client = build_groq_client()
                resp = client.chat.completions.create(
                    model=MODELS_CATALOG["groq-gpt-oss-120b"]["modele"],
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    max_tokens=max_output_tokens,
                )
                text = (resp.choices[0].message.content or "").strip()
                if resp.usage:
                    usage_in = resp.usage.prompt_tokens or 0
                    usage_out = resp.usage.completion_tokens or 0

            elif provider_id == "ollama":
                client = build_ollama_client()
                resp = client.chat(
                    model=MODELS_CATALOG.get(provider_id, {}).get("modele", "llama3.2:1b"),
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    options={"num_predict": max_output_tokens},
                )
                text = (resp["message"]["content"] or "").strip()

            else:
                return {"text": "", "usage_in": 0, "usage_out": 0,
                        "ok": False, "erreur": f"Fournisseur inconnu: {provider_id}"}

            dur = perf_counter() - start
            return {"text": text or "", "usage_in": usage_in, "usage_out": usage_out,
                    "ok": True, "erreur": None, "duree_s": dur}
        except Exception as exc:  # noqa: BLE001 — le benchmark doit toujours remonter
            last_err = f"{type(exc).__name__}: {exc}"
            is_quota = "429" in last_err or "RESOURCE_EXHAUSTED" in last_err
            if not is_quota:
                break
            if essai < retry_429:
                time.sleep(backoff_base * (2 ** essai))  # 8 s, 16 s, 32 s…
    return {"text": "", "usage_in": 0, "usage_out": 0,
            "ok": False, "erreur": last_err}


# ---------------------------------------------------------------------------
# Jeu d'évaluation
# ---------------------------------------------------------------------------

def load_eval_set() -> list[dict]:
    """Charge le jeu d'évaluation JSON (questions grounded)."""
    raw = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    return raw["questions"]


def build_prompt(question: dict, instruction: str) -> tuple[str, str]:
    """Construit (system, user) pour une question.

    Le contexte fourni est volontairement STRICT : la réponse doit s'appuyer sur
    le contexte. `instruction` précise la tâche (défaut : répondre avec citation
    d'article).
    """
    system = (
        "Tu es un assistant spécialisé en marchés publics au Togo. Réponds "
        "UNIQUEMENT à partir du CONTEXTE fourni. Si l'information n'est pas dans "
        "le contexte, dis-le explicitement. Cite les articles concernés (ex. "
        "'Article 12') lorsque tu t'appuies sur eux. Ne fais aucune supposition "
        "hors du contexte.\n\n" + instruction
    )
    user = (
        "CONTEXTE (extrait de textes de la commande publique du Togo) :\n"
        "---\n"
        f"{question['contexte']}\n"
        "---\n\n"
        f"Question : {question['question']}"
    )
    return system, user


# ---------------------------------------------------------------------------
# Scoring automatique des critères observables sans juge
# ---------------------------------------------------------------------------

def score_citations(reponse: str, citation_attendue: list[str]) -> float:
    """1.0 si au moins une citation attendue est présente, 0 sinon, 0.5 si une
    citation « proche » (numéro d'article attendu dans un intitulé voisin)."""
    if not citation_attendue:
        return 1.0  # pas de citation attendue → neutre
    lowered = reponse.lower()
    for c in citation_attendue:
        if c.lower() in lowered:
            return 1.0
    # Corrige le cas où le modèle cite "article 111" comme "article 110" — on
    # vérifie le numéro seul, plutôt pénalisant (0.5) : c'est un écart.
    for c in citation_attendue:
        num = re.search(r"(\d+)", c)
        if num and num.group(1) in reponse:
            return 0.5
    return 0.0


def _negation_travaux(reponse: str) -> bool:
    """Détecte une formulation du type « (n'est) pas/jamais exigée pour les travaux ».

    La clause contenant « exigée/requise/… » doit précéder « travaux » dans la
    même proposition, et contenir un marqueur de négation (frontières de mot :
    `\bne\b` ne matche pas « boNNE ») — évite les faux positifs (« est exigée pour
    les travaux » sans négation) comme les faux négatifs (« n'est JAMAIS exigée »).
    """
    lowered = reponse.lower()
    for mot in ("exigée", "exigee", "exigé", "exige", "requise", "requis",
                "obligatoire", "applicable"):
        m = re.search(r"([^.;]{0,40})" + mot + r"[^.;]*?(?:travaux)", lowered)
        if m and re.search(r"\b(pas|jamais|non|ne|n'est|n’est)\b", m.group(1)):
            return True
    return False


def score_piege_grounding(reponse: str, question: dict) -> float:
    """Pour les questions pièges : 1.0 si le modèle suit le contexte piégé
    (répond 'non', '2 %', 'fournitures'), 0.0 sinon (il reprend sa connaissance)."""
    lowered = reponse.lower()
    a_non_travaux = _negation_travaux(reponse)
    a_fournitures = r"\bfournitures\b" in lowered
    a_2pct = re.search(r"2\s*%|deux\s+pour\s+cent", lowered) is not None
    # Suit le contexte piège si : fournitures + 2 %, ou négation liée aux travaux + 2 %.
    return 1.0 if (a_fournitures or a_non_travaux) and a_2pct else 0.0


def score_info_absente(reponse: str, question: dict) -> float:
    """Pour les questions 'info absente' : 1.0 si le modèle déclare ne pas
    savoir (honnêteté), 0.0 s'il invente."""
    reconnu_inconnu = re.search(
        r"(ne (le )?pr[eé]cise|(n'|n’)?est (pas|jamais) pr[eé]cis[ée]?|"
        r"(pas|non) pr[eé]cis[ée]?|introuvable|inconnu|"
        r"pas (d'|de )?information|ne (le )?(mentionne|dit|précise) |"
        r"contient pas|absent du contexte|pas dans le contexte|"
        r"ne (le )?pr[eé]cise pas|aucune (date|indication|information))",
        reponse, re.IGNORECASE)
    invente_delai = re.search(r"\b\d+\s*(jours|mois)\b", reponse, re.IGNORECASE)
    if reconnu_inconnu and not invente_delai:
        return 1.0
    if reconnu_inconnu and invente_delai:
        return 0.3  # hésitant, a failli inventer
    return 0.0


def score_faits_presents(reponse: str, question: dict) -> float:
    """Proportion des faits attendus (closures terminologiques) présents dans la
    réponse. Utile pour valider que le modèle a bien repris les éléments du
    contexte (grounding positif, pas seulement 'pas d'hallucination')."""
    faits = question.get("faits_attendus", [])
    if not faits:
        return 1.0
    lowered = reponse.lower()
    found = [f for f in faits if f.lower() in lowered]
    return len(found) / len(faits)


SCORES_AUTOMATIQUES = {
    "grounding_piege": score_piege_grounding,
    "info_absente": score_info_absente,
    "citation": score_citations,
    "faits": score_faits_presents,
}


# ---------------------------------------------------------------------------
# Juge LLM — notation qualitative (français, grounding global, format)
# ---------------------------------------------------------------------------
# Par défaut, le juge est Gemini 3.5 Flash (un autre fournisseur que Groq) ;
# quand on juge Gemini lui-même, il est préférable de désigner un juge distinct
# (ex. Groq) pour éviter l'auto-évaluation — l'utilisateur peut le régler.

JUDGE_SYSTEM = (
    "Tu es un évaluateur rigoureux de réponses d'assistants juridiques en marchés "
    "publics togolais. Tu dois noter objectivement, en te basant sur le label "
    "d'évaluation fourni ET sur le contexte donné. Réponds STRICTEMENT au format :"
    "\nLangue (0-5) : x\nConformité (0-5) : x\nFormat (0-5) : x\nEffort (0-2)OK"
)


def score_juge_llm(provider_id: str, question: dict, reponse: str) -> dict:
    """Renvoie les scores du juge : {"langue":0-5, "conformite":0-5,
    "format":0-5, "ok":bool, "erreur":str}. Sans juge dispo → -1 (à évaluer
    manuellement)."""
    if not question.get("label_pour_juge"):
        return {"langue": -1, "conformite": -1, "format": -1, "ok": False,
                "erreur": "pas de label_pour_juge"}
    system = JUDGE_SYSTEM
    user = (
        "CONTEXTE fourni à l'assistant :\n---\n"
        f"{question['contexte']}\n---\n\n"
        f"Question : {question['question']}\n\n"
        f"LABEL d'évaluation :\n{question['label_pour_juge']}\n\n"
        "RÉPONSE À ÉVALUER :\n" + reponse
    )
    res = call_model(provider_id, system, user, max_output_tokens=600)
    if not res["ok"]:
        return {"langue": -1, "conformite": -1, "format": -1,
                "ok": False, "erreur": res["erreur"]}
    txt = res["text"]
    langue = _extraire_entier_apres(txt, "Langue")
    conformite = _extraire_entier_apres(txt, "Conformité") or \
        _extraire_entier_apres(txt, "Conformite")
    format_ = _extraire_entier_apres(txt, "Format")
    return {"langue": langue if langue is not None else -1,
            "conformite": conformite if conformite is not None else -1,
            "format": format_ if format_ is not None else -1,
            "ok": None not in (langue, conformite, format_), "erreur": None}


def _extraire_entier_apres(texte: str, mot: str) -> int | None:
    """Extrait la première valeur numérique juste après 'mot :'."""
    m = re.search(re.escape(mot) + r"\s*[:=]\s*(\d+)", texte)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Pondérations des critères et note finale
# ---------------------------------------------------------------------------

DEFAULT_POIDS = {
    "grounding": 0.25,
    "citations": 0.20,
    "robustesse": 0.20,
    "langue": 0.10,
    "latence": 0.10,
    "quotas": 0.10,
    "cout": 0.05,
}


def calcule_note_finale(scores: dict[str, float], poids: dict[str, float] | None = None) -> float:
    """Note finale pondérée sur 10. Les scores manquants (-1, NaN) sont ignorés
    et les poids restants renormalisés."""
    p = {**DEFAULT_POIDS, **(poids or {})}
    total = 0.0
    masse = 0.0
    for crit, s in scores.items():
        if s is None or (isinstance(s, float) and (s < 0 or s != s)):
            continue
        masse += p.get(crit, 0)
        total += p.get(crit, 0) * s * 10  # s entre 0 et 1 → note sur 10
    return total / masse if masse else 0.0