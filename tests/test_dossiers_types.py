"""
Tests du scraping des dossiers-types ARCOP (arcop.tg/dossiers-types/).

Local, sans réseau : on parse la fixture data/fixtures/dossiers_types.html qui
reproduit la structure réellement observée (blocs <details> + tables TablePress,
hreff avec espaces en tête, numéros entre parenthèses).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper_dossiers_types import parse_dossiers_types  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "dossiers_types.html"


def test_parse_extracts_all_dossiers():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_dossiers_types(html)
    assert len(results) == 6, f"Attendu 6 dossiers, obtenu {len(results)}"


def test_parse_extracts_categories():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_dossiers_types(html)
    categories = {d.categorie for d in results}
    assert categories == {"Dossiers types DP", "Dossiers typesTravaux"}


def test_parse_extracts_numero_and_libelle():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_dossiers_types(html)
    dao_travaux = next(d for d in results if "DAO Travaux" in d.libelle)
    assert dao_travaux.numero == "1"
    assert dao_travaux.libelle == "DAO TravauxFnal"


def test_parse_strips_href():
    """Le site réel contient des espaces en tête dans certains href — on doit les
    supprimer et produire une URL absolue propre."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_dossiers_types(html)
    preselection = next(d for d in results if "preselection" in d.libelle)
    assert preselection.url_fichier == (
        "https://arcop.tg/wp-content/uploads/2026/02/"
        "3Dossier_standard_de_preselection_togoFnal.docx"
    )
    assert preselection.url_fichier == preselection.url_fichier.strip()


def test_parse_handles_dossier_without_numero():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_dossiers_types(html)
    sans_numero = next(d for d in results if d.url_fichier.endswith("DP-Type-marches-importants.docx"))
    assert sans_numero.numero is None
    assert sans_numero.libelle == "DP-Type-marches-importants"


if __name__ == "__main__":
    test_parse_extracts_all_dossiers()
    test_parse_extracts_categories()
    test_parse_extracts_numero_and_libelle()
    test_parse_strips_href()
    test_parse_handles_dossier_without_numero()
    print("Tous les tests locaux passent.")