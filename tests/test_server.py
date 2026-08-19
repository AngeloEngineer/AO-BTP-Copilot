"""Tests du serveur (Étape A) — auth, base de données, aiguillage RAG.

Aucun réseau : les appels Ollama/embedding sont masqués par des fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for p in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from server import auth, db, rag  # noqa: E402


# --- Authentification (PBKDF2 + JWT, aucune dépendance réseau) --------------


def test_hash_verify_password():
    h = auth.hash_password("MotDePasse123")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("MotDePasse123", h)
    assert not auth.verify_password("mauvais", h)


def test_token_roundtrip():
    tok = auth.creer_token(7, "jeanne@btma.ci")
    payload = auth.decoder_token(tok)
    assert payload["sub"] == "7"
    assert payload["email"] == "jeanne@btma.ci"


def test_verify_password_rejette_format_illisible():
    assert not auth.verify_password("x", "n'importe quoi")


# --- Base de données --------------------------------------------------------


@pytest.fixture
def base(tmp_path):
    b = db.Database(tmp_path / "app.db")
    b.init_schema()
    return b


def test_cycle_utilisateur_conversation_messages(base):
    u = base.creer_utilisateur("jeanne@btma.ci", "Jeanne", "hash")
    assert u["email"] == "jeanne@btma.ci"

    conv = base.creer_conversation(u["id"], "Premier marché")
    assert conv["user_id"] == u["id"]

    base.ajouter_message(conv["id"], "user", "Bonjour")
    base.ajouter_message(conv["id"], "assistant", "Bonjour ! Posez votre question.")
    roles = [m["role"] for m in base.messages_par_conversation(conv["id"])]
    assert roles == ["user", "assistant"]

    liste = base.conversations_par_user(u["id"])
    assert liste[0]["nb_messages"] == 2
    assert liste[0]["titre"] == "Premier marché"

    base.supprimer_conversation(conv["id"], u["id"])
    assert base.messages_par_conversation(conv["id"]) == []


def test_email_minuscule_et_unicite(base):
    u = base.creer_utilisateur("  JEANNE@BTMA.CI ", "Jeanne", "h")
    assert u["email"] == "jeanne@btma.ci"
    assert base.utilisateur_par_email("Jeanne@btma.ci")["id"] == u["id"]


def test_renommer_conversation_respecte_propriete(base):
    u1 = base.creer_utilisateur("a@btma.ci", "A", "h")
    u2 = base.creer_utilisateur("b@btma.ci", "B", "h")
    conv = base.creer_conversation(u1["id"])

    assert base.renommer_conversation(conv["id"], u2["id"], "Pirate") is None
    renamed = base.renommer_conversation(conv["id"], u1["id"], "Renommé")
    assert renamed["titre"] == "Renommé"


# --- RAG : aiguillage résumé/checklist/chat (index simulé, aucun réseau) ----


class _FakeIndex:
    def rechercher(self, question, k=6):
        return [{
            "source": "test.pdf",
            "document": "decret-2022-080-code-marches-publics",
            "article": "12",
            "titre": "Seuils",
            "texte": "Le seuil de passation des marchés de travaux est fixé par décret.",
        }] * k


_AO = {
    "reference": "AO-2026-00009",
    "titre": "Forages solaires",
    "objet": "Réalisation de forages et aménagements",
    "entite": "ARAA",
    "type_marche": "Travaux",
    "statut": "Publié",
    "date_limite": "10/07/2026",
}


@pytest.fixture
def rag_offline(monkeypatch):
    monkeypatch.setattr(rag, "charger_index", lambda: _FakeIndex())
    monkeypatch.setattr(rag, "charger_consultations", lambda: [dict(_AO)])
    return rag


def test_intention_resume_avec_marche(rag_offline):
    p = rag_offline.construire_prompt("Résumé de ce marché", "AO-2026-00009", [])
    assert p["intention"] == "resume"
    assert p["introduction"] == ""
    assert "Forages solaires" in p["user"]  # fiche AO incluse


def test_intention_checklist_sans_marche_renvoie_introduction(rag_offline):
    p = rag_offline.construire_prompt("Checklist d'éligibilité", "general", [])
    assert p["intention"] == "checklist"
    assert "sélectionner un marché" in p["introduction"]


def test_intention_chat_general_pas_de_fiche(rag_offline):
    p = rag_offline.construire_prompt(
        "Quel est le seuil fixé par décret ?", "general",
        [{"role": "user", "content": "Bonjour"}],
    )
    assert p["intention"] == "chat"
    assert "FICHE DE L'APPEL D'OFFRES" not in p["user"]
    assert "Bonjour" in p["user"]  # historique passé au prompt


def test_historique_recent_borne():
    msgs = [{"role": "user" if i % 2 else "assistant", "content": str(i)}
            for i in range(20)]
    h = rag.historique_recent(msgs)
    assert len(h) == 6
    assert h[0]["content"] == str(14)


def test_generer_stream_vide_sur_introduction():
    # construction réservée au cas « introduction » : aucun appel modèle
    assert list(rag.generer_ollama_stream("...", "...")) == []