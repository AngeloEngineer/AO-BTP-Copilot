"""Classification BTP/Travaux partagée entre les scrapers.

Classifieur à base de règles (mots-clés), pas de ML : les étiquettes officielles des
sites sources sont incomplètes ou absentes (ex. arcop.tg n'a même pas de champ
"type_marche" — juste une catégorie "Actualités" générique), et le vocabulaire du
domaine des marchés publics est normalisé et sans ambiguïté. Un modèle entraîné
n'apporterait aucune valeur ici ; le classifieur sert de filet de sécurité derrière
l'étiquette du site quand elle existe et qu'on peut lui faire confiance.
"""

from __future__ import annotations

import re

BTP_KEYWORDS = [
    "travaux", "construction", "réhabilitation", "rehabilitation", "réfection", "refection",
    "bâtiment", "batiment", "génie civil", "genie civil", "voirie", "assainissement",
    "forage", "aménagement", "amenagement", "électrification", "electrification",
    "route", "pont", "ouvrage", "barrage", "irrigation",
    "revêtement", "revetement", "adduction d'eau", "bitumage", "pavage",
    # "réseau" seul est trop ambiguë (ex. "Réseau africain de la commande publique" —
    # un nom d'organisation, pas une infrastructure). On ne matche que des expressions
    # composées sans ambiguïté, repérées lors des tests (voir test_scraper_arcop.py).
    # Singulier ET pluriel car les deux formes apparaissent dans les AO réels observés.
    "réseau d'assainissement", "réseaux d'assainissement", "réseau électrique",
    "réseaux électriques", "réseau routier", "réseaux routiers", "réseau de distribution",
    "réseaux de distribution", "réseaux solaires", "mini-réseau", "mini-réseaux",
    "réseau d'eau", "reseau d'assainissement", "reseaux d'assainissement",
    "reseau electrique", "reseau routier",
]
BTP_KEYWORDS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in BTP_KEYWORDS) + r")\b", re.IGNORECASE
)


def classify_btp(titre: str, type_marche_site: str | None) -> tuple[bool, str | None]:
    """Détermine si une consultation relève du BTP/Travaux, en croisant l'étiquette du
    site (fiable quand présente et exploitable) et une détection lexicale sur le titre
    (filet de sécurité quand l'étiquette est absente, trompeuse, ou inexistante).

    Retourne (is_btp, source) où source vaut "site", "mots-clés" ou None.
    """
    if type_marche_site and type_marche_site.strip() not in ("", "—"):
        is_travaux = type_marche_site.strip().lower() == "travaux"
        return is_travaux, "site" if is_travaux else None

    if BTP_KEYWORDS_PATTERN.search(titre):
        return True, "mots-clés"

    return False, None