"""Schémas Pydantic de l'API (validation entrée / sortie)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# --- Auth -------------------------------------------------------------------

class RegisterRequest(BaseModel):
    nom: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    nom: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    token: str
    user: UserOut


# --- Conversations ----------------------------------------------------------

class ConversationCreate(BaseModel):
    titre: str = Field(default="Nouvelle discussion", max_length=200)


class ConversationRename(BaseModel):
    titre: str = Field(min_length=1, max_length=200)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ConversationOut(BaseModel):
    id: int
    titre: str
    created_at: str
    updated_at: str
    nb_messages: int = 0
    messages: list[MessageOut] = []


# --- Chat -------------------------------------------------------------------

class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    marche: str | None = None  # référence d'AO ou "general"
    pays: str = "Togo"  # phase A : corpus principal togolais