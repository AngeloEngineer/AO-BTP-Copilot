"""Exporte l'index FAISS + métadonnées + consultations vers la démo web statique.

Produit, dans deploy/webgpu-demo/assets/ :
  - vectors.b64.txt : le tensor float32 entier de l'index encodé en base64
                      (lignes = chunks, même ordre que meta.json, lignes normalisées)
  - meta.json       : métadonnées des chunks (document, article, titre, texte)
  - consultations.json
  - config.json     : dim, nb_chunks, modèle d'embedding

Usage :  .venv\\Scripts\\python.exe scripts/export_demo_web.py
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAISS_DIR = ROOT / "data" / "processed" / "faiss"
CONSULTATIONS_DB = ROOT / "data" / "processed" / "consultations.db"
OUT_DIR = ROOT / "deploy" / "webgpu-demo" / "assets"


def main() -> None:
    import faiss

    index = faiss.read_index(str(FAISS_DIR / "index.faiss"))
    dim, ntot = index.d, index.ntotal
    import numpy as np

    arr = np.empty((ntot, dim), dtype="float32")
    index.reconstruct_n(0, ntot, arr)  # lignes = chunks (déjà normalisées)

    meta = json.loads((FAISS_DIR / "meta.json").read_text(encoding="utf-8"))
    if len(meta) != ntot:
        raise SystemExit(f"meta.json ({len(meta)}) != index.faiss ({ntot}) chunks")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "vectors.b64.txt").write_text(
        base64.b64encode(arr.tobytes()).decode("ascii")
    )
    (OUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )

    consultations: list[dict] = []
    if CONSULTATIONS_DB.exists():
        conn = sqlite3.connect(CONSULTATIONS_DB)
        conn.row_factory = sqlite3.Row
        consultations = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM consultations ORDER BY date_limite DESC"
            )
        ]
        conn.close()
    (OUT_DIR / "consultations.json").write_text(
        json.dumps(consultations, ensure_ascii=False), encoding="utf-8"
    )

    cfg = {
        "dim": dim,
        "nb_chunks": ntot,
        "modele_embedder": "paraphrase-multilingual-MiniLM-L12-v2",
        "index_type": "FlatIP_normalized",
    }
    (OUT_DIR / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"export ok : {ntot}x{dim} vecteurs "
          f"({round(len(arr.tobytes()) / 1e6, 2)} Mo brute), "
          f"{len(meta)} meta, {len(consultations)} consultations -> {OUT_DIR}")


if __name__ == "__main__":
    main()