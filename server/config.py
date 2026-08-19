"""Config du serveur AO-BTP Copilot (Étape A — service web multi-utilisateur)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

# Base de données applicative (utilisateurs, conversations, messages)
APP_DB = DATA_DIR / "app.db"

# Base des avis d'appel d'offres (créée par la couche ingestion)
CONSULTATIONS_DB = DATA_DIR / "consultations.db"

# Entreprise unique de l'étape A (plusieurs employés y créent un compte)
COMPANY_NAME = "Btma Industries"

# JWT (en production : fournir JWT_SECRET dans l'environnement, ≥ 32 octets)
JWT_SECRET = os.environ.get(
    "JWT_SECRET",
    "btma-dev-secret-a-changer-0123456789abcdef-0123456789",  # 48 octets, dev only
)
JWT_ALGO = "HS256"
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", "720"))  # 12 h

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODELE = "llama3.2:1b"  # modèle de génération local (décision produit 18/08)

HISTORIQUE_MAX_TOURS = 6  # mémoire de conversation envoyée au modèle
MAX_OUTPUT_TOKENS = 1000  # borne de sortie par génération