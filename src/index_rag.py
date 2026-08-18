"""
Index FAISS local du corpus RAG.

À partir des chunks (`corpus_chunks.json`) et d'un embedder (`embeddings.py`),
construit un **index vectoriel local FAISS**, le sauvegarde sur disque, et offre
la recherche top-k : à une question, encode la question en vecteur, cherche les
k chunks les plus proches (similarité de cosinus) et renvoie les métadonnées
(document, article, titre, texte).

Choix documentés §19 (FAISS local, pas de vector DB cloud) et §38.3.

Stockage :
    {répertoire}/index.faiss     — index FAISS (fichier binaire)
    {répertoire}/meta.json       — métadonnées des chunks (même ordre)
    {répertoire}/config.json     — modèle d'embedding, dim, source

Usage typique (CLI) :
    python src/index_rag.py --chunks data/processed/corpus_chunks.json \
        --dir data/processed/faiss/ --backend mock          # tests / pas de modèle
    python src/index_rag.py --chunks data/processed/corpus_chunks.json \
        --dir data/processed/faiss/ --backend local         # modèle multilingue
    python src/index_rag.py --query "seuils de passation" --dir data/processed/faiss/ -k 5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from embeddings import creer_embedder, texte_chunk


def _import_faiss():
    """Import différé (lourd) ; lève une erreur claire si absent."""
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "faiss n'est pas installé. "
            "Exécutez :  .venv\\Scripts\\python -m pip install faiss-cpu numpy"
        ) from exc
    return faiss


def normaliser(vecteurs: list[list[float]]) -> "object":
    """Convertit list[list[float]] en array float32 (FAISS exige float32)."""
    import numpy as np

    return np.asarray(vecteurs, dtype="float32")


def resoudre_backend(repertoire: Path, backend: str | None = "auto") -> str:
    """Backend effectif pour la recherche : suit config.json si demandé (auto)."""
    if backend != "auto":
        return backend
    cfg = Path(repertoire) / "config.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8"))["backend"]
    raise FileNotFoundError(
        f"config.json introuvable dans {repertoire} — précisez --backend"
    )


class IndexRAG:
    """Index FAISS + métadonnées des chunks, sauvegardable / rechargeable."""

    def __init__(self, embedder, dim: int):
        self.embedder = embedder
        self.dim = dim
        faiss = _import_faiss()
        # IndexFlatIP + vecteurs normalisés ⇒ recherche par similarité de cosinus
        self.index = faiss.IndexFlatIP(dim)
        self.metadonnees: list[dict] = []

    # --- construction ------------------------------------------------------

    @classmethod
    def construire(cls, embedder, chunks: list[dict]) -> "IndexRAG":
        """Crée l'index à partir des chunks (les embédde, puis ajoute)."""
        textes = [texte_chunk(c) for c in chunks]
        if not textes:
            raise ValueError("aucun chunk à indexer")
        vecteurs = normaliser(embedder.embeddings(textes))
        self = cls(embedder=embedder, dim=vecteurs.shape[1])
        self.index.add(vecteurs)
        self.metadonnees = list(chunks)
        return self

    # --- persistance -------------------------------------------------------

    def sauvegarder(self, repertoire: Path, config: dict | None = None) -> Path:
        """Écrit index.faiss + meta.json (+ config.json) dans `repertoire`."""
        repertoire = Path(repertoire)
        repertoire.mkdir(parents=True, exist_ok=True)
        index_path = repertoire / "index.faiss"
        faiss = _import_faiss()
        faiss.write_index(self.index, str(index_path))
        (repertoire / "meta.json").write_text(
            json.dumps(self.metadonnees, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        if config is not None:
            (repertoire / "config.json").write_text(
                json.dumps(config, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        return index_path

    @classmethod
    def charger(cls, repertoire: Path, embedder) -> "IndexRAG":
        """Recharge un index sauvegardé + ses métadonnées."""
        repertoire = Path(repertoire)
        faiss = _import_faiss()
        self = cls.__new__(cls)
        self.embedder = embedder
        self.index = faiss.read_index(str(repertoire / "index.faiss"))
        self.dim = self.index.d
        self.metadonnees = json.loads(
            (repertoire / "meta.json").read_text(encoding="utf-8")
        )
        return self

    # --- recherche ---------------------------------------------------------

    def rechercher(self, question: str, k: int = 5) -> list[dict]:
        """Retourne les k chunks les plus proches, avec score de similarité."""
        if not self.index.ntotal:
            return []
        vq = normaliser(self.embedder.embeddings([question]))
        scores, idx = self.index.search(vq, min(k, self.index.ntotal))
        resultats = []
        for score, pos in zip(scores[0], idx[0]):
            if pos < 0:
                continue
            meta = dict(self.metadonnees[int(pos)])
            meta["score"] = float(score)
            resultats.append(meta)
        return resultats

    def __len__(self) -> int:
        return self.index.ntotal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="commande", required=True)

    p_build = sub.add_parser("build", help="construire l'index depuis les chunks")
    p_build.add_argument("--chunks", type=Path, required=True,
                         help="corpus_chunks.json")
    p_build.add_argument("--dir", type=Path, default=Path("data/processed/faiss"),
                         help="répertoire de sortie")
    p_build.add_argument("--backend", default="local",
                         help="local | ollama | mock")
    p_build.add_argument("--modele", default=None,
                         help="modèle d'embedding (défaut selon backend)")
    p_build.add_argument("--source", default=None,
                         help="champ source conservé dans config.json")

    p_q = sub.add_parser("query", help="rechercher dans un index existant")
    p_q.add_argument("--dir", type=Path, required=True)
    p_q.add_argument("--query", required=True, help="question / requête")
    p_q.add_argument("-k", type=int, default=5)
    p_q.add_argument("--backend", default="auto",
                     help="local | ollama | mock | auto (défaut : lit config.json)")

    args = parser.parse_args()

    if args.commande == "build":
        from embeddings import charger_chunks

        chunks = charger_chunks(args.chunks)
        kwargs = {"modele": args.modele} if args.modele else {}
        embedder = creer_embedder(args.backend, **kwargs)
        index = IndexRAG.construire(embedder, chunks)
        config = {
            "backend": args.backend,
            "modele": getattr(embedder, "modele", None),
            "dim": index.dim,
            "nb_chunks": len(chunks),
            "source": args.source or str(args.chunks),
        }
        p = index.sauvegarder(args.dir, config=config)
        print(f"Index FAISS : {len(index)} chunks, dim {index.dim} → {p}")

    elif args.commande == "query":
        kwargs = {}
        args.backend = resoudre_backend(args.dir, args.backend)
        embedder = creer_embedder(args.backend, **kwargs)
        index = IndexRAG.charger(args.dir, embedder)
        print(f"{len(index)} chunks indexés — requête : {args.query!r}")
        for r in index.rechercher(args.query, k=args.k):
            print(f"\nscore={r['score']:.4f} | {r['document']} "
                  f"art. {r['article']} | {r.get('titre', '')[:60]}")
            print(f"   {r['texte'][:200]}…")


if __name__ == "__main__":
    main()
