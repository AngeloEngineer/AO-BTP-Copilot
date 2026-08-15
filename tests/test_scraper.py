"""
Test local du parsing (pas d'accès réseau requis). Valide la logique d'extraction contre
la fixture reconstituée. À compléter/corriger dès que le HTML réel du site est capturé
en environnement avec accès réseau (J1, priorité 1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper import parse_consultations_table, classify_btp  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "consultations_list.html"


def test_parse_consultations_table_extracts_all_rows():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_consultations_table(html)
    assert len(results) == 4, f"Attendu 4 lignes, obtenu {len(results)}"


def test_parse_consultations_table_fields():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_consultations_table(html)
    first = results[0]
    assert first.reference == "AO-2026-00009"
    assert "Forages à énergie solaire" in first.titre
    assert first.type_marche == "Travaux"
    assert first.date_limite == "10/07/2026"
    assert first.url_detail.startswith("https://www.marches-publics-togo.com/consultations/")


def test_parse_filters_travaux_correctly():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_consultations_table(html)
    travaux_site = [c for c in results if c.type_marche == "Travaux"]
    assert len(travaux_site) == 2  # AO-2026-00009 et AO-2026-00003 dans la fixture


def test_classify_btp_catches_mislabeled_tender():
    """Cas réel qui a motivé ce classifieur : AO-2026-00007 a type_marche="—" côté
    site, mais son titre commence par "Travaux de réalisation de réseaux
    d'assainissement..." — sans le classifieur mots-clés, cet AO travaux serait
    perdu."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_consultations_table(html)
    ao_7 = next(c for c in results if c.reference == "AO-2026-00007")
    assert ao_7.type_marche == "—"
    assert ao_7.is_btp is True
    assert ao_7.btp_classification_source == "mots-clés"


def test_classify_btp_direct_unit_cases():
    assert classify_btp("Fourniture de mobiliers de bureau", "Fournitures") == (False, None)
    assert classify_btp("Travaux de réfection de la voirie", None) == (True, "mots-clés")
    assert classify_btp("Prestation de nettoyage", "Travaux") == (True, "site")


def test_all_btp_via_is_btp_flag():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_consultations_table(html)
    btp = [c for c in results if c.is_btp]
    # AO-2026-00009 (site), AO-2026-00007 (mots-clés), AO-2026-00003 (site) = 3
    assert len(btp) == 3, f"Attendu 3 AO classifiés BTP, obtenu {len(btp)}"


if __name__ == "__main__":
    test_parse_consultations_table_extracts_all_rows()
    test_parse_consultations_table_fields()
    test_parse_filters_travaux_correctly()
    test_classify_btp_catches_mislabeled_tender()
    test_classify_btp_direct_unit_cases()
    test_all_btp_via_is_btp_flag()
    print("Tous les tests locaux passent.")