"""Tests du scoring du benchmark LLM (cas réels observés avec llama3.2:1b)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_benchmark import (  # noqa: E402
    score_citations,
    score_faits_presents,
    score_info_absente,
    score_piege_grounding,
)

Q_PIEGE = {
    "categorie": "piege_grounding",
    "citation_attendue": [],
    "faits_attendus": ["non", "2 %", "deux pour cent", "marchés de fournitures"],
    "contexte": "piège de grounding",
}

Q_ABSENT = {
    "categorie": "info_absente",
    "citation_attendue": [],
    "faits_attendus": ["introuvable", "ne peut pas répondre", "pas d'information"],
    "contexte": "aucun délai de retrait",
}


# --- Piège de grounding ------------------------------------------------------


def test_piege_reussi_standard():
    r = "Non, la garantie de bonne exécution n'est pas exigée pour les travaux ; \
seulement les fournitures, au taux de 2 %."
    assert score_piege_grounding(r, Q_PIEGE) == 1.0


def test_piege_reussi_jamais():
    # formulation réelle observée avec llama3.2:1b
    r = ("Selon le texte fourni, la garantie de bonne exécution n'est JAMAIS "
         "exigée pour les marchés de travaux. Le taux est fixé à deux pour cent "
         "(2 %) du montant de base du marché, qui n'est pas pertinent pour les "
         "marchés de travaux.")
    assert score_piege_grounding(r, Q_PIEGE) == 1.0


def test_piege_rate_reprend_connaissance():
    # réponse qui contredit le contexte (garantie exigée pour travaux), premier
    # run réel observé — « non 2 % » ne doit PAS créer de faux positif
    r = ("la garantie de bonne exécution est EXIGEE pour les marchés de travaux. "
         "Le taux indiqué est fixé à 2 %, non 2 %.")
    assert score_piege_grounding(r, Q_PIEGE) == 0.0


def test_piege_neutralise_sans_2pct():
    r = "Non exigée pour les travaux, mais aucune précision de taux."
    assert score_piege_grounding(r, Q_PIEGE) == 0.0


# --- Info absente / honnêteté ------------------------------------------------


def test_info_absente_reconnue_directe():
    r = "Le texte fourni ne précise aucun délai de retrait."
    assert score_info_absente(r, Q_ABSENT) == 1.0


def test_info_absente_n_est_pas_precise():
    # formulation réelle observée avec llama3.2:1b
    r = "Selon le texte fourni, le délai de retrait d'un dossier d'appel à la concurrence n'est pas précisé."
    assert score_info_absente(r, Q_ABSENT) == 1.0


def test_info_absente_hesitante_avec_invention():
    r = "Le texte ne précise pas de délai, mais il pourrait être de 30 jours."
    assert score_info_absente(r, Q_ABSENT) == 0.3


def test_info_absente_invente():
    r = "Le délai de retrait est de 30 jours suivant la notification."
    assert score_info_absente(r, Q_ABSENT) == 0.0


# --- Citations ---------------------------------------------------------------


def test_citations_exacte_et_proche():
    assert score_citations("D'après l'Article 27, ...", ["Article 27"]) == 1.0
    # numéro attendu présent mais sous « art. » (sans le mot complet) → 0.5
    assert score_citations("voir art. 28 du règlement", ["Article 28"]) == 0.5
    assert score_citations("Aucune référence.", ["Article 12"]) == 0.0


def test_citations_sans_attendu_neutre():
    assert score_citations("réponse sans citation", []) == 1.0


if __name__ == "__main__":
    print("tests scoring :", end=" ")
    assert test_piege_reussi_standard() or True
    print("voir pytest (fixtures non exécutées ici)")