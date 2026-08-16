"""
Scraper pour les avis d'appel d'offres / manifestations d'intérêt publiés par l'ARCOP
(Autorité de Régulation de la Commande Publique togolaise) sur arcop.tg/appels-doffres/.

Structure différente de marches-publics-togo.com : ce n'est pas une table de données
mais un flux d'articles WordPress/Elementor. Chaque entrée a un titre-lien, une date en
toutes lettres ("6 mai 2025"), et souvent un lien PDF directement dans le texte
d'accroche (ex. "Cliquez sur le lien suivant pour lire l'AMI https://.../AMI-XXX.pdf") —
ce qui permet parfois de récupérer le PDF sans même visiter la page de détail.

Pas de champ "type_marche" du tout sur ce site (juste une catégorie générique
"Actualités") : la classification BTP repose donc entièrement sur les mots-clés,
appliqués au titre ET au texte d'accroche pour maximiser le rappel.

IMPORTANT (contexte sandbox) : comme pour scraper.py, ce module est écrit à partir de
la structure réellement observée (via un outil de fetch web qui convertit en markdown,
pas de DOM brut) mais n'a pas tourné en direct depuis cet environnement. À valider en
premier lors de l'exécution réelle, sélecteurs à ajuster si besoin.

Usage :
    python src/scraper_arcop.py --out data/processed/consultations_arcop.db
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from http_client import fetch_html, log
from classification import BTP_KEYWORDS_PATTERN

BASE_URL = "https://arcop.tg"
LISTING_PATH = "/appels-doffres/"

# Dates en toutes lettres, ex. "6 mai 2025" — format observé sur le site.
FRENCH_MONTHS = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    "septembre|octobre|novembre|décembre|decembre"
)
DATE_PATTERN = re.compile(rf"(\d{{1,2}}\s+(?:{FRENCH_MONTHS})\s+\d{{4}})", re.IGNORECASE)
PDF_LINK_PATTERN = re.compile(r"https?://\S+\.pdf", re.IGNORECASE)


@dataclass
class ArcopEntry:
    titre: str
    url_detail: str
    date_publication: str | None
    pdf_url_direct: str | None  # trouvé directement dans l'accroche, sans visiter le détail
    scraped_at: str
    is_btp: bool
    btp_classification_source: str | None  # "mots-clés" ou None (pas d'étiquette site ici)


def parse_arcop_listing(html: str, base_url: str = BASE_URL) -> list[ArcopEntry]:
    """Parse le flux d'articles de la page /appels-doffres/.

    Stratégie : chaque entrée est ancrée sur un <h3> (titre d'article, confirmé par la
    structure observée) contenant un lien vers l'article complet. Le texte d'accroche
    et la date sont recherchés dans le voisinage immédiat de ce titre plutôt que par une
    classe CSS précise (plus robuste aux changements mineurs de mise en page Elementor).
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[ArcopEntry] = []
    now = datetime.now(timezone.utc).isoformat()

    for heading in soup.find_all("h3"):
        link = heading.find("a")
        if not link or not link.has_attr("href"):
            continue

        titre = link.get_text(strip=True)
        if len(titre) < 15:
            continue  # probablement un titre de menu/widget, pas un article

        url_detail = urljoin(base_url, link["href"])

        # Voisinage textuel : on regarde le texte des ~3 éléments frères suivants pour
        # y trouver la date et un éventuel lien PDF direct, sans dépendre d'une classe
        # CSS précise qui peut changer.
        nearby_text_parts = []
        sibling = heading.find_next_sibling()
        hops = 0
        while sibling is not None and hops < 4:
            nearby_text_parts.append(sibling.get_text(" ", strip=True))
            sibling = sibling.find_next_sibling()
            hops += 1
        nearby_text = " ".join(nearby_text_parts)

        date_match = DATE_PATTERN.search(nearby_text)
        date_publication = date_match.group(1) if date_match else None

        pdf_match = PDF_LINK_PATTERN.search(nearby_text)
        pdf_url_direct = pdf_match.group(0) if pdf_match else None

        combined_text_for_classification = f"{titre} {nearby_text}"
        is_btp = bool(BTP_KEYWORDS_PATTERN.search(combined_text_for_classification))
        btp_source = "mots-clés" if is_btp else None

        results.append(
            ArcopEntry(
                titre=titre,
                url_detail=url_detail,
                date_publication=date_publication,
                pdf_url_direct=pdf_url_direct,
                scraped_at=now,
                is_btp=is_btp,
                btp_classification_source=btp_source,
            )
        )

    return results


def scrape_arcop(btp_only: bool = False) -> list[ArcopEntry]:
    url = urljoin(BASE_URL, LISTING_PATH)
    log.info("Récupération de %s", url)
    html = fetch_html(url)

    entries = parse_arcop_listing(html)
    n_btp = sum(1 for e in entries if e.is_btp)
    log.info("%d entrée(s) au total sur arcop.tg — %d classées BTP (mots-clés).", len(entries), n_btp)

    if btp_only:
        entries = [e for e in entries if e.is_btp]
    return entries


def save_to_sqlite(entries: list[ArcopEntry], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arcop_entries (
            url_detail TEXT PRIMARY KEY,
            titre TEXT NOT NULL,
            date_publication TEXT,
            pdf_url_direct TEXT,
            scraped_at TEXT NOT NULL,
            is_btp INTEGER NOT NULL DEFAULT 0,
            btp_classification_source TEXT
        )
        """
    )
    for e in entries:
        row = asdict(e)
        row["is_btp"] = int(row["is_btp"])
        conn.execute(
            """
            INSERT INTO arcop_entries (url_detail, titre, date_publication, pdf_url_direct,
                scraped_at, is_btp, btp_classification_source)
            VALUES (:url_detail, :titre, :date_publication, :pdf_url_direct,
                :scraped_at, :is_btp, :btp_classification_source)
            ON CONFLICT(url_detail) DO UPDATE SET
                titre=excluded.titre,
                date_publication=excluded.date_publication,
                pdf_url_direct=excluded.pdf_url_direct,
                scraped_at=excluded.scraped_at,
                is_btp=excluded.is_btp,
                btp_classification_source=excluded.btp_classification_source
            """,
            row,
        )
    conn.commit()
    conn.close()
    log.info("Sauvegardé dans %s", db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btp-only", action="store_true")
    parser.add_argument("--out", default="data/processed/consultations_arcop.db")
    args = parser.parse_args()

    entries = scrape_arcop(btp_only=args.btp_only)
    for e in entries:
        tag = " [BTP]" if e.is_btp else ""
        pdf = f" | PDF: {e.pdf_url_direct}" if e.pdf_url_direct else ""
        print(f"- {e.titre[:70]}{tag} ({e.date_publication}){pdf}")

    save_to_sqlite(entries, Path(args.out))


if __name__ == "__main__":
    main()