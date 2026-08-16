"""
Scraper des dossiers-types publiés par l'ARCOP (Autorité de Régulation de la Commande
Publique togolaise) sur arcop.tg/dossiers-types/.

Pourquoi ce scraper : après évaluation de arcop.tg/appels-doffres/ (constats documentés
dans PROGRESS.md et test_scraper_arcop.py), le volume d'AO Travaux *en cours* publié au
Togo est structurellement faible. Les dossiers-types sont des DOCUMENTS BTP par nature
(modèles officiels de DAO, RP, présélection...), publiés par l'autorité de régulation :
ils n'ont besoin d'aucune classification incertaine par mots-clés (contrairement aux AO),
et servent de référentiel authentique aux couches aval (extraction, RAG).

Structure observée (page WordPress + Elementor + plugin TablePress) :
- la page contient 4 blocs <details><summary> (catégories), chacun englobant une table
  TablePress au format : N° | Libellé | Télécharger.
- le libellé est préfixé d'un numéro entre parenthèses ex. "(1) DAO Travaux".
- le fichier téléchargeable est un <a class="btn"> dont le href peut contenir des espaces
  en tête (on fait .strip() systématiquement).

Usage :
    python src/scraper_dossiers_types.py --out data/processed/dossiers_types.db
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

BASE_URL = "https://arcop.tg"
DOSSIERS_TYPES_PATH = "/dossiers-types/"

# Numéros de dossier fréquents au début du libellé, ex. "(1)" ou "(11)".
NUMERO_PATTERN = re.compile(r"^\s*\((\d+)\)\s*")


@dataclass
class DossierType:
    numero: str | None
    libelle: str
    categorie: str
    url_fichier: str
    scraped_at: str


def parse_dossiers_types(html: str, base_url: str = BASE_URL) -> list[DossierType]:
    """Parse les 4 blocs <details> de la page /dossiers-types/.

    Chaque bloc <details> = une catégorie (summary) + une table TablePress.
    Une ligne : N° | Libellé | bouton de téléchargement.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[DossierType] = []
    now = datetime.now(timezone.utc).isoformat()

    for details in soup.find_all("details"):
        summary = details.find("summary")
        if summary is None:
            continue
        categorie = summary.get_text(strip=True)
        if not categorie:
            continue

        table = details.find("table")
        if table is None:
            log.warning("Catégorie '%s' sans table, ignorée.", categorie[:40])
            continue

        for tr in table.find_all("tr")[1:]:  # on saute la ligne d'en-tête
            libelle_cell = tr.find("td", class_="column-2")
            download_cell = tr.find("td", class_="column-3")
            if libelle_cell is None or download_cell is None:
                continue

            libelle_raw = libelle_cell.get_text(strip=True)
            if not libelle_raw:
                continue

            link = download_cell.find("a", href=True)
            if link is None:
                continue

            url_fichier = urljoin(base_url, link["href"].strip())
            numero_match = NUMERO_PATTERN.match(libelle_raw)
            numero = numero_match.group(1) if numero_match else None
            libelle = NUMERO_PATTERN.sub("", libelle_raw, count=1).strip()

            results.append(
                DossierType(
                    numero=numero,
                    libelle=libelle,
                    categorie=categorie,
                    url_fichier=url_fichier,
                    scraped_at=now,
                )
            )

    return results


def scrape_dossiers_types() -> list[DossierType]:
    url = urljoin(BASE_URL, DOSSIERS_TYPES_PATH)
    log.info("Récupération de %s", url)
    html = fetch_html(url)

    dossiers = parse_dossiers_types(html)
    log.info("%d dossier(s)-type trouvé(s) sur %d catégorie(s).", len(dossiers),
             len({d.categorie for d in dossiers}))
    return dossiers


def save_to_sqlite(dossiers: list[DossierType], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dossiers_types (
            url_fichier TEXT PRIMARY KEY,
            numero TEXT,
            libelle TEXT NOT NULL,
            categorie TEXT NOT NULL,
            scraped_at TEXT NOT NULL
        )
        """
    )
    for d in dossiers:
        conn.execute(
            """
            INSERT INTO dossiers_types (url_fichier, numero, libelle, categorie, scraped_at)
            VALUES (:url_fichier, :numero, :libelle, :categorie, :scraped_at)
            ON CONFLICT(url_fichier) DO UPDATE SET
                numero=excluded.numero,
                libelle=excluded.libelle,
                categorie=excluded.categorie,
                scraped_at=excluded.scraped_at
            """,
            asdict(d),
        )
    conn.commit()
    conn.close()
    log.info("Sauvegardé dans %s", db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/processed/dossiers_types.db")
    args = parser.parse_args()

    dossiers = scrape_dossiers_types()
    for d in dossiers:
        print(f"[{d.categorie[:30]}] {d.numero or '—'} | {d.libelle[:60]}")

    save_to_sqlite(dossiers, Path(args.out))


if __name__ == "__main__":
    main()