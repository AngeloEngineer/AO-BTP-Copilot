"""
Téléchargement des documents sources vers le stockage local data/raw/.

Deux types de documents :
- les dossiers-types ARCOP (.docx) — modèles officiels BTP publiés par l'autorité de
  régulation, listés dans data/processed/dossiers_types.db ;
- le corpus légal (PDF) — Recueil des textes de la commande publique, édition 2024.

Principes :
- téléchargement avec le client HTTP partagé (http_client.py) ;
- nom de fichier local dérivé de l'URL (slug basé sur le nom original) ;
- re-téléchargement seulement si le fichier est absent (idempotent).

Usage :
    python src/download_documents.py --dossiers data/processed/dossiers_types.db
    python src/download_documents.py --corpus-legal
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from http_client import fetch_html, log

# Chemin par défaut du stockage des documents bruts (hors git, voir .gitignore).
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Corpus légal principal : Recueil des textes de la commande publique (édition 2024).
CORPUS_LEGAL_URL = (
    "https://arcop.tg/wp-content/uploads/2025/10/"
    "RECUEIL-DES-TEXTES-DE-LA-COMMANDE-PUBLIQUE-EDITION-2024-ARCOP-PDF-2.pdf"
)

# Extension à conserver selon l'URL : on cherche l'extension sur le nom de fichier
# "propre" (sans query string ni fragment).
EXTENSION_PATTERN = re.compile(r"\.(docx?|pdf|odt|zip)$", re.IGNORECASE)


def _local_filename(url: str) -> str:
    """Transforme une URL de fichier en nom de fichier local propre.

    Ex. https://arcop.tg/.../1-DAO-TravauxFnal-1.docx -> 1-DAO-TravauxFnal-1.docx
    """
    # Supprime d'abord la query string / fragment éventuels.
    clean_url = url.split("?", 1)[0].split("#", 1)[0]
    name = clean_url.rstrip("/").rsplit("/", 1)[-1]
    extension = EXTENSION_PATTERN.search(name)
    base = name if extension else name + ".bin"
    # Nettoie les caractères illégaux pour Windows et les espaces.
    return re.sub(r'[<>:"/\\|?*]', "_", base).strip()


def download_file(url: str, dest_dir: Path, force: bool = False,
                  retries: int = 3, delay: float = 1.0) -> Path | None:
    """Télécharge un fichier vers dest_dir (idempotent si le fichier existe déjà).

    Petites défenses pour un téléchargement de masse sur un site distant :
    - retries avec backoff souple en cas de timeout/erreur réseau transitoire ;
    - latence d'attente avant chaque requête (politesse serveur + espacement).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / _local_filename(url)

    if dest_path.exists() and not force:
        log.debug("Existe déjà, ignoré : %s", dest_path.name)
        return dest_path

    # fetch_html ne convient pas ici (il retourne le texte de la réponse) : on récupère
    # le contenu binaire via requests directement, mais avec les mêmes conventions
    # (headers, timeout). On réutilise HEADERS/REQUEST_TIMEOUT du client partagé.
    from http_client import HEADERS, REQUEST_TIMEOUT
    import time
    import requests as _requests

    for attempt in range(1, retries + 1):
        try:
            resp = _requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
            log.info("Téléchargé : %s (%d octets)", dest_path.name, len(resp.content))
            return dest_path
        except (_requests.RequestException, OSError) as exc:
            if attempt == retries:
                log.error("Échec définitif après %d tentative(s) : %s (%s)",
                          retries, url, exc)
                return None
            wait = delay * attempt
            log.warning("Tentative %d/%d échouée pour %s — nouvel essai dans %.1fs",
                        attempt, retries, url, wait)
            time.sleep(wait)
    return None


def download_dossiers_types(db_path: Path, dest_dir: Path | None = None,
                            force: bool = False) -> list[Path]:
    """Télécharge tous les dossiers-types listés dans la base SQLite."""
    dest_dir = dest_dir or RAW_DIR / "dossiers_types"
    sqlite3.connect(str(db_path))  # vérifie l'ouverture tôt

    conn = sqlite3.connect(str(db_path))
    urls = [r[0] for r in conn.execute("SELECT url_fichier FROM dossiers_types")]
    conn.close()

    downloaded: list[Path] = []
    for url in urls:
        path = download_file(url, dest_dir, force=force)
        if path is not None:
            downloaded.append(path)
    log.info("%d dossier(s)-type téléchargé(s) ou déjà présents.", len(downloaded))
    return downloaded


def download_corpus_legal(dest_dir: Path | None = None, force: bool = False) -> Path | None:
    """Télécharge le corpus légal (Recueil ARCOP 2024)."""
    dest_dir = dest_dir or RAW_DIR / "corpus_legal"
    return download_file(CORPUS_LEGAL_URL, dest_dir, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dossiers", metavar="DB",
        help="Télécharge les dossiers-types listés dans cette base SQLite",
    )
    parser.add_argument("--corpus-legal", action="store_true", help="Télécharge le corpus légal PDF")
    parser.add_argument("--force", action="store_true", help="Force le re-téléchargement")
    args = parser.parse_args()

    if args.dossiers:
        download_dossiers_types(Path(args.dossiers), force=args.force)
    if args.corpus_legal:
        download_corpus_legal(force=args.force)


if __name__ == "__main__":
    main()