"""Client HTTP partagé entre les scrapers (marches-publics-togo.com, arcop.tg, ...).

Mutualisé ici plutôt que dupliqué : dès qu'un 2e, ou 3e ou n-ième scraper existe, la logique de fetch
(headers, timeout, gestion d'erreur) devient un vrai composant commun, pas juste un
copier-coller.
"""

from __future__ import annotations

import logging

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# User-Agent identifiable et honnête : bonne pratique de scraping, pas une formalité.
HEADERS = {
    "User-Agent": (
        "AO-BTP-Copilot/0.1 (usage non commercial)"
    )
}

REQUEST_TIMEOUT = 15
POLITE_DELAY_SECONDS = 1.5  # entre deux requêtes, pour ne pas marteler le serveur


def fetch_html(url: str, params: dict | None = None) -> str:
    """Récupère le HTML d'une page. Lève une exception explicite en cas d'échec
    plutôt que de renvoyer une chaîne vide silencieusement."""
    resp = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text