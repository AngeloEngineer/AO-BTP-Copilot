"""
Embeddings du corpus RAG.

Un embedding transforme un texte en **vecteur de nombres** (liste de flottants)
qui capture son sens : deux textes sémantiquement proches produisent des vecteurs
proches. Les chunks d'articles (`corpus_chunks.json`) sont passés à un modèle
d'embedding ; les vecteurs résultants seront indexés par FAISS (`index_rag.py`).

Modèle par défaut : `paraphrase-multilingual-MiniLM-L12-v2` (384 dims,
multilingue FR inclus, ~470 MB, **local et gratuit**). Choix documenté §18/§38.4.

Architecture pluggable (même interface `Embedder` / `embeddings`()) :
- `LocalSentenceEmbedder` : sentence-transformers local (par défaut) ;
- `OllamaEmbedder` : via l'API Ollama (modèle d'embedding, ex. `nomic-embed-text`) ;
- `MockEmbedder` : faux vecteurs déterministes → tests rapides sans télécharger
  de modèle (imports faiss/torch en différé).

Usage typique :
    embed = LocalSentenceEmbedder()          # télécharge le modèle au 1er appel
    vecs  = embed.embeddings(["article 1", "article 2"])   # (2, 384)
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    """Contrat minimal : transformer des textes en matrice de vecteurs."""

    def embeddings(self, textes: list[str]) -> "object":
        """Retourne un array (n_textes, dim) normalisable en `list[list[float]]`."""


def charger_chunks(chemin: Path) -> list[dict]:
    """Charge `corpus_chunks.json` et renvoie la liste des chunks."""
    import json

    data = json.loads(Path(chemin).read_text(encoding="utf-8"))
    return data["chunks"]


def texte_chunk(chunk: dict) -> str:
    """Représentation texte d'un chunk (ce qu'on va embédder)."""
    titre = chunk.get("titre") or ""
    return f"{titre} {chunk['texte']}".strip()


class LocalSentenceEmbedder:
    """Embeddings via sentence-transformers, modèle multilingue local."""

    def __init__(self, modele: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.modele = modele
        self._enc = None

    def _encoder(self):
        if self._enc is None:
            from sentence_transformers import SentenceTransformer  # import lourd

            self._enc = SentenceTransformer(self.modele)
        return self._enc

    def embeddings(self, textes: list[str]):
        return self._encoder().encode(textes, normalize_embeddings=True)


class OllamaEmbedder:
    """Embeddings via Ollama (modèle d'embedding local, API HTTP)."""

    def __init__(self, modele: str = "nomic-embed-text", base_url: str = None):
        self.modele = modele
        self.base_url = base_url
        self._client = None

    def _cl(self):
        if self._client is None:
            import ollama

            kwargs = {"base_url": self.base_url} if self.base_url else {}
            self._client = ollama.Client(**kwargs)
        return self._client

    def embeddings(self, textes: list[str]):
        vecs = []
        for t in textes:
            r = self._cl().embed(model=self.modele, input=t)
            vecs.append(r["embeddings"][0])
        return vecs


class MockEmbedder:
    """Faux embeddings déterministes (tests uniquement, aucun modèle requis)."""

    def __init__(self, dim: int = 16):
        self.dim = dim

    def embeddings(self, textes: list[str]):
        import hashlib

        vecs = []
        for t in textes:
            h = hashlib.sha256(t.encode("utf-8")).digest()[: self.dim]
            v = [b / 255.0 for b in h]
            vecs.append(v)
        return vecs


def creer_embedder(backend: str = "local", **kwargs) -> Embedder:
    """Fabrique un embedder selon `backend` : local | ollama | mock."""
    backend = (backend or "local").lower()
    if backend == "local":
        return LocalSentenceEmbedder(**kwargs)
    if backend == "ollama":
        return OllamaEmbedder(**kwargs)
    if backend == "mock":
        return MockEmbedder(**kwargs)
    raise ValueError(f"backend inconnu : {backend!r}")
