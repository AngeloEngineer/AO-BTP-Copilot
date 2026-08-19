"""Accès SQLite du serveur — utilisateurs, conversations, messages.

Fichier unique `data/processed/app.db`, isolé des bases d'ingestion
(consultations.db / extraction.db / dossiers_types.db) pour rester remplaçable
par Postgres lorsque le volume (multi-entreprise) l'exigera.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    nom           TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    titre      TEXT NOT NULL DEFAULT 'Nouvelle discussion',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Connexion SQLite par appel (thread-safe, connexions courtes).

    SQLite gère le multi-connexions ; chaque itération ouvre une connexion neuve,
    ce qui évite tout partage d'état entre requêtes (utile dès que FastAPI
    fait tourner plusieurs threads).
    """

    def __init__(self, chemin: Path):
        self.chemin = str(chemin)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.chemin)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        self.chemin = str(Path(self.chemin))
        parent = Path(self.chemin).parent
        parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # -- utilisateurs --------------------------------------------------------

    def creer_utilisateur(self, email: str, nom: str, password_hash: str) -> dict:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, nom, password_hash, created_at) "
                "VALUES (?, ?, ?, ?)",
                (email.lower().strip(), nom.strip(), password_hash, _now()),
            )
            # même connexion/transaction : la ligne est visible sans commit séparé
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)

    def utilisateur_par_email(self, email: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
            ).fetchone()
            return dict(row) if row else None

    def utilisateur_par_id(self, user_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    # -- conversations -------------------------------------------------------

    def creer_conversation(self, user_id: int, titre: str = "Nouvelle discussion") -> dict:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, titre, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, titre, _now(), _now()),
            )
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)

    def conversation_par_id(self, conversation_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return dict(row) if row else None

    def conversations_par_user(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m "
                "             WHERE m.conversation_id = c.id) AS nb_messages "
                "FROM conversations c WHERE c.user_id = ? "
                "ORDER BY c.updated_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def renommer_conversation(self, conversation_id: int, user_id: int,
                              titre: str) -> dict | None:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET titre = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (titre.strip(), _now(), conversation_id, user_id),
            )
            if not cur.rowcount:
                return None
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return dict(row)

    def supprimer_conversation(self, conversation_id: int, user_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            return cur.rowcount > 0

    # -- messages ------------------------------------------------------------

    def ajouter_message(self, conversation_id: int, role: str, content: str) -> dict:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, _now()),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (_now(), conversation_id),
            )
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)

    def messages_par_conversation(self, conversation_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? "
                "ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
            return [dict(r) for r in rows]