import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper_arcop import parse_arcop_listing  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "arcop_listing.html"


def test_parse_extracts_all_entries():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_arcop_listing(html)
    assert len(results) == 3, f"Attendu 3 entrées, obtenu {len(results)}"


def test_parse_extracts_date_and_pdf_link():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_arcop_listing(html)
    audit_entry = next(r for r in results if "audit" in r.titre.lower())
    assert audit_entry.date_publication == "25 avril 2025"
    assert audit_entry.pdf_url_direct == "https://arcop.tg/wp-content/uploads/2025/04/AMI-AUDIT-2024.pdf"


def test_honest_finding_no_btp_in_this_sample():
    """Constat important à documenter, pas juste un test technique : les 3 entrées
    réelles observées sur arcop.tg/appels-doffres/ sont toutes des AMI de recrutement
    de consultants (chef de projet, audit, refonte de site web) — aucune n'est un AO
    Travaux/BTP. Ce test vérifie que le classifieur ne force pas un faux positif ; il
    documente aussi que cette page seule ne résout probablement pas le problème de
    volume BTP à elle seule (voir PROGRESS.md)."""

    html = FIXTURE_PATH.read_text(encoding="utf-8")
    results = parse_arcop_listing(html)
    btp_entries = [r for r in results if r.is_btp]
    assert len(btp_entries) == 0


if __name__ == "__main__":
    test_parse_extracts_all_entries()
    test_parse_extracts_date_and_pdf_link()
    test_honest_finding_no_btp_in_this_sample()
    print("Tous les tests locaux passent.")