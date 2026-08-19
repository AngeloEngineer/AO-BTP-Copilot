"""Serveur AO-BTP Copilot — API REST + streaming SSE + frontend statique.

Étape A : service web multi-utilisateur pour l'entreprise « Btma Industries ».
Chaque employé crée un compte (email + mot de passe), puis converse avec le
bot RAG (résumé / checklist / chat) en temps réel (SSE).

Lancement :  .venv\\Scripts\\python.exe -m uvicorn server.main:app --reload
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.auth import (  # noqa: E402
    UtilisateurAuth,
    creer_token,
    hash_password,
    utilisateur_courant,
    verify_password,
)
from server.config import APP_DB, COMPANY_NAME  # noqa: E402
from server.db import Database  # noqa: E402
from server import rag  # noqa: E402
from server.schemas import (  # noqa: E402
    ConversationCreate,
    ConversationOut,
    ConversationRename,
    LoginRequest,
    MessageCreate,
    RegisterRequest,
    TokenOut,
    UserOut,
)

db = Database(APP_DB)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_schema()
    yield


app = FastAPI(title="AO-BTP Copilot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    if db.utilisateur_par_email(body.email):
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")
    user = db.creer_utilisateur(body.email, body.nom, hash_password(body.password))
    return TokenOut(token=creer_token(user["id"], user["email"]), user=UserOut(**user))


@app.post("/api/auth/login", response_model=TokenOut)
def login(body: LoginRequest):
    user = db.utilisateur_par_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return TokenOut(token=creer_token(user["id"], user["email"]), user=UserOut(**user))


@app.get("/api/auth/me", response_model=UserOut)
def me(user: UtilisateurAuth = Depends(utilisateur_courant)):
    return UserOut(id=user.id, email=user.email, nom=user.nom)


@app.get("/api/meta")
def meta():
    return {"entreprise": COMPANY_NAME, "nb_marches": len(rag.charger_consultations()),
            "modele": "Ollama local llama3.2:1b"}


# ---------------------------------------------------------------------------
# Consultations (AO réels)
# ---------------------------------------------------------------------------

@app.get("/api/consultations")
def lister_consultations(pays: str | None = None):
    consultations = rag.charger_consultations()
    if pays:
        consultations = [c for c in consultations if c.get("pays", "Togo") == pays]
    return consultations


# ---------------------------------------------------------------------------
# Conversations (multi-utilisateur)
# ---------------------------------------------------------------------------

def _verifier_propriete(conversation_id: int, user: UtilisateurAuth) -> dict:
    conversation = db.conversation_par_id(conversation_id)
    if conversation is None or conversation["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return conversation


@app.get("/api/conversations")
def lister_conversations(user: UtilisateurAuth = Depends(utilisateur_courant)):
    return db.conversations_par_user(user.id)


@app.post("/api/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def creer_conversation(body: ConversationCreate,
                       user: UtilisateurAuth = Depends(utilisateur_courant)):
    conv = db.creer_conversation(user.id, body.titre)
    return ConversationOut(**conv)


@app.get("/api/conversations/{conversation_id}", response_model=ConversationOut)
def detail_conversation(conversation_id: int,
                        user: UtilisateurAuth = Depends(utilisateur_courant)):
    conv = _verifier_propriete(conversation_id, user)
    messages = db.messages_par_conversation(conversation_id)
    return ConversationOut(**conv, nb_messages=len(messages), messages=messages)


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationOut)
def renommer_conversation(conversation_id: int, body: ConversationRename,
                          user: UtilisateurAuth = Depends(utilisateur_courant)):
    conv = db.renommer_conversation(conversation_id, user.id, body.titre)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    messages = db.messages_par_conversation(conversation_id)
    return ConversationOut(**conv, nb_messages=len(messages), messages=messages)


@app.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_conversation(conversation_id: int,
                           user: UtilisateurAuth = Depends(utilisateur_courant)):
    if not db.supprimer_conversation(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")


# ---------------------------------------------------------------------------
# Message + génération (streaming SSE)
# ---------------------------------------------------------------------------

@app.post("/api/conversations/{conversation_id}/messages")
def poster_message(conversation_id: int, body: MessageCreate,
                   user: UtilisateurAuth = Depends(utilisateur_courant)):
    conv = _verifier_propriete(conversation_id, user)

    # premier message → titre automatique de la conversation
    avant = db.messages_par_conversation(conversation_id)
    if not avant:
        db.renommer_conversation(conversation_id, user.id,
                                 body.content.strip()[:48])

    db.ajouter_message(conversation_id, "user", body.content)
    historique = rag.historique_recent(avant)

    def evenements():
        def envoyer(payload: dict) -> str:
            return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

        try:
            prompt = rag.construire_prompt(body.content, body.marche, historique)
            if prompt.get("introduction"):
                yield envoyer({"type": "delta", "content": prompt["introduction"]})
                yield envoyer({"type": "done"})
                db.ajouter_message(conversation_id, "assistant",
                                   prompt["introduction"])
                return

            brut = ""
            try:
                for fragment in rag.generer_ollama_stream(prompt["system"], prompt["user"]):
                    brut += fragment
                    yield envoyer({"type": "delta", "content": fragment})
            except Exception as exc:  # noqa: BLE001 — Ollama arrêté, modèle absent…
                message_erreur = (
                    "Impossible d'obtenir une réponse : "
                    f"{exc}. Vérifiez que le serveur Ollama tourne et que le "
                    "modèle est installé (ollama pull llama3.2:1b)."
                )
                brut = message_erreur
                yield envoyer({"type": "error", "content": message_erreur})

            brut = brut.strip()
            if brut:
                db.ajouter_message(conversation_id, "assistant", brut)
                avertissements = lf_verifier_references(brut)
                if avertissements:
                    yield envoyer({"type": "warnings", "content": avertissements})
            yield envoyer({"type": "done"})
        except Exception as exc:  # noqa: BLE001 — erreur applicative hors génération
            yield envoyer({"type": "error", "content": f"Erreur interne : {exc}"})
            yield envoyer({"type": "done"})

    return StreamingResponse(evenements(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def lf_verifier_references(texte: str) -> list[str]:
    import llm_features as lf
    return lf.verifier_references(texte)


# ---------------------------------------------------------------------------
# Frontend statique (build Vite) — servi à la racine en production
# ---------------------------------------------------------------------------

_DIST = _PROJECT_ROOT / "web" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{chemin:path}", include_in_schema=False)
    def spa(chemin: str):
        fichier = _DIST / chemin
        if chemin and fichier.is_file() and "_SPA_" not in str(fichier.resolve()):
            return FileResponse(fichier)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)