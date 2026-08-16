"""
Scraper pour les avis d'appel d'offres (AO) publics togolais, filtrés sur le type
"Travaux" (BTP au sens large : bâtiment, génie civil, routes, hydraulique...).

Source primaire : marches-publics-togo.com — plateforme neuve (03/2026), structure HTML
propre. La page /consultations expose une table HTML sémantique en plus des "cards"
visuelles (probablement une version accessible/fallback) : on l'utilise en priorité car
plus stable dans le temps qu'un ciblage par classes CSS.

IMPORTANT (contexte sandbox) : ce module n'a pas encore été exécuté contre le site en
direct (pas d'accès réseau à ce domaine depuis l'environnement de développement de
Claude). Les sélecteurs sont écrits défensivement (table en priorité, fallback sur les
cards) à partir de la structure réellement observée via un outil de fetch web, mais DOIVENT
être validés/ajustés en conditions réelles lors du J1. C'est une étape normale du scraping,
pas un signe d'échec du design.

Usage :
    python src/scraper.py --type-marche Travaux --out data/processed/consultations.db
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from http_client import fetch_html, log
from classification import classify_btp

BASE_URL = "https://www.marches-publics-togo.com"
CONSULTATIONS_PATH = "/consultations"


@dataclass
class Consultation:
    reference: str
    titre: str
    entite: str | None
    type_marche: str | None
    statut: str | None
    date_limite: str | None
    url_detail: str
    scraped_at: str
    is_btp: bool = False
    btp_classification_source: str | None = None  # "site" | "mots-clés" | None


def fetch_html(url: str, params: dict | None = None) -> str:
    """Récupère le HTML d'une page. Lève une exception explicite en cas d'échec
    plutôt que de renvoyer une chaîne vide silencieusement."""
    resp = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_consultations_table(html: str, base_url: str = BASE_URL) -> list[Consultation]:
    """Parse la table sémantique de la page /consultations.

    Colonnes attendues (ordre observé) : Référence | Titre (lien) | Entité | Type |
    Statut | Date limite | (lien détail, souvent dupliqué en dernière colonne).

    Retourne une liste vide si aucune table n'est trouvée (le fallback cards prend
    le relais côté appelant), plutôt que de lever une exception : l'absence de table
    est une situation attendue à gérer, pas une erreur.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        log.warning("Aucune <table> trouvée — la structure a peut-être changé.")
        return []

    rows = table.find_all("tr")
    results: list[Consultation] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        cells = row.find_all(["td"])
        if len(cells) < 5:
            continue  # ligne d'en-tête ou ligne incomplète, on ignore proprement

        reference = cells[0].get_text(strip=True)

        titre_cell = cells[1]
        titre_link = titre_cell.find("a")
        titre = titre_link.get_text(strip=True) if titre_link else titre_cell.get_text(strip=True)
        href = titre_link["href"] if titre_link and titre_link.has_attr("href") else None
        url_detail = urljoin(base_url, href) if href else ""

        entite = cells[2].get_text(strip=True) or None
        type_marche = cells[3].get_text(strip=True) or None
        statut = cells[4].get_text(strip=True) or None
        date_limite = cells[5].get_text(strip=True) if len(cells) > 5 else None

        if not reference or not url_detail:
            log.warning("Ligne ignorée (référence ou lien manquant) : %s", titre[:60])
            continue

        is_btp, btp_source = classify_btp(titre, type_marche)

        results.append(
            Consultation(
                reference=reference,
                titre=titre,
                entite=entite,
                type_marche=type_marche,
                statut=statut,
                date_limite=date_limite,
                url_detail=url_detail,
                scraped_at=now,
                is_btp=is_btp,
                btp_classification_source=btp_source,
            )
        )

    return results


def parse_consultations_cards(html: str, base_url: str = BASE_URL) -> list[Consultation]:
    """Fallback si la table sémantique disparaît un jour : parse les blocs "card"
    (titre en <h3>/<h2>, référence + date en texte libre à proximité).

    Volontairement plus permissif et donc plus fragile — à ne considérer que comme
    filet de sécurité, à valider manuellement si utilisé.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[Consultation] = []
    now = datetime.now(timezone.utc).isoformat()

    for heading in soup.find_all(["h2", "h3"]):
        link = heading.find("a") or heading.find_parent("a")
        if not link or not link.has_attr("href"):
            continue
        titre = link.get_text(strip=True)
        href = urljoin(base_url, link["href"])

        # La référence (ex. "AO-2026-00009") apparaît souvent juste avant/après le titre
        context_text = heading.find_next(string=re.compile(r"AO-\d{4}-\d+")) 
        reference_match = re.search(r"AO-\d{4}-\d+", context_text) if context_text else None
        reference = reference_match.group(0) if reference_match else href.rstrip("/").rsplit("/", 1)[-1]

        results.append(
            Consultation(
                reference=reference,
                titre=titre,
                entite=None,
                type_marche=None,
                statut=None,
                date_limite=None,
                url_detail=href,
                scraped_at=now,
            )
        )

    return results


def scrape_consultations(btp_only: bool = False) -> list[Consultation]:
    """Point d'entrée principal : récupère TOUTES les consultations (pas de filtre
    serveur — voir docstring de classify_btp sur pourquoi le champ type_marche du site
    n'est pas fiable à 100%), puis classifie chacune BTP/non-BTP.

    Si `btp_only=True`, ne retourne que celles jugées BTP (site OU mots-clés).
    """
    url = urljoin(BASE_URL, CONSULTATIONS_PATH)
    log.info("Récupération de %s (liste complète, sans filtre serveur)", url)
    html = fetch_html(url)

    consultations = parse_consultations_table(html)
    if not consultations:
        log.info("Table vide/absente, tentative avec le parsing cards (fallback).")
        consultations = parse_consultations_cards(html)

    n_site = sum(1 for c in consultations if c.btp_classification_source == "site")
    n_kw = sum(1 for c in consultations if c.btp_classification_source == "mots-clés")
    log.info(
        "%d consultation(s) au total — %d BTP via étiquette site, %d BTP via mots-clés (rattrapées).",
        len(consultations), n_site, n_kw,
    )

    if btp_only:
        consultations = [c for c in consultations if c.is_btp]
    return consultations


def save_to_sqlite(consultations: list[Consultation], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS consultations (
            reference TEXT PRIMARY KEY,
            titre TEXT NOT NULL,
            entite TEXT,
            type_marche TEXT,
            statut TEXT,
            date_limite TEXT,
            url_detail TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            is_btp INTEGER NOT NULL DEFAULT 0,
            btp_classification_source TEXT
        )
        """
    )
    for c in consultations:
        row = asdict(c)
        row["is_btp"] = int(row["is_btp"])  # SQLite n'a pas de type bool natif
        conn.execute(
            """
            INSERT INTO consultations (reference, titre, entite, type_marche, statut,
                date_limite, url_detail, scraped_at, is_btp, btp_classification_source)
            VALUES (:reference, :titre, :entite, :type_marche, :statut, :date_limite,
                :url_detail, :scraped_at, :is_btp, :btp_classification_source)
            ON CONFLICT(reference) DO UPDATE SET
                titre=excluded.titre,
                entite=excluded.entite,
                type_marche=excluded.type_marche,
                statut=excluded.statut,
                date_limite=excluded.date_limite,
                url_detail=excluded.url_detail,
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
    parser.add_argument(
        "--btp-only", action="store_true",
        help="Ne garder que les consultations classifiées BTP (site ou mots-clés)",
    )
    parser.add_argument(
        "--out", default="data/processed/consultations.db", help="Chemin de la base SQLite"
    )
    args = parser.parse_args()

    consultations = scrape_consultations(btp_only=args.btp_only)
    for c in consultations:
        tag = f" [BTP:{c.btp_classification_source}]" if c.is_btp else ""
        print(f"- [{c.reference}] {c.titre[:70]}{tag} (limite: {c.date_limite})")

    save_to_sqlite(consultations, Path(args.out))


if __name__ == "__main__":
    main()