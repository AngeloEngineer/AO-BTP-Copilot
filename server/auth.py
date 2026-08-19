"""Authentification — mots de passe (PBKDF2, stdlib) + JWT (PyJWT).

Une seule entreprise au stade A (« Btma Industries ») ; chaque employé crée un
compte (email + mot de passe) et reçoit un JWT pour les appels suivants.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_ALGO, JWT_EXP_MINUTES, JWT_SECRET

_ITERS = 200_000
_SALT_LEN = 16

_bearer = HTTPBearer(auto_error=False)


@dataclass
class UtilisateurAuth:
    id: int
    email: str
    nom: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERS)
    return f"pbkdf2_sha256${_ITERS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters_b64, salt_b64, hash_b64 = stored.split("$")
        iters = int(iters_b64)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def creer_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXP_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decoder_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])


def utilisateur_courant(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                        ) -> UtilisateurAuth:
    """Dépendance FastAPI : renvoie l'utilisateur authentifié ou 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentification requise")
    try:
        payload = decoder_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token invalide ou expiré")
    from .db import Database
    from .config import APP_DB

    row = Database(APP_DB).utilisateur_par_id(user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Utilisateur inconnu")
    return UtilisateurAuth(id=row["id"], email=row["email"], nom=row["nom"])