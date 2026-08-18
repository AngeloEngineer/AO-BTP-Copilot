"""Benchmark RÉEL d'un modèle Ollama local sur le jeu d'évaluation.

Alternative légère au notebook `notebooks/benchmark_llm.ipynb` pour le cas
Ollama (qui n'a pas besoin de clé) : exécute les 7 questions grounded, calcule
les scores automatiques (grounding piège / honnêteté / citations / faits) et
affiche les réponses brutes pour l'échantillon manuel.

Usage :
    python scripts/benchmark_ollama_reel.py [--modele llama3.2:1b] [--max-tokens 600]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import llm_benchmark as lb  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modele", default="llama3.2:1b")
    parser.add_argument("--max-tokens", type=int, default=600)
    args = parser.parse_args()

    # Le modèle est transmis via le catalogue (le noyau le lit pour ollama).
    lb.MODELS_CATALOG["ollama"]["modele"] = args.modele
    print(f"Modèle : {args.modele} — {args.max_tokens} tokens max / réponse\n")

    questions = lb.load_eval_set()
    lignes_csv = []
    for q in questions:
        system, user = lb.build_prompt(q, "")
        t0 = time.perf_counter()
        res = lb.call_model("ollama", system, user,
                            max_output_tokens=args.max_tokens)
        dt = time.perf_counter() - t0
        if not res["ok"]:
            print(f"{q['id']} : ÉCHEC — {res['erreur'][:200]}")
            continue

        rep = res["text"]
        c = q.get("categorie")
        s = {
            "piège": 1.0 if c != "piege_grounding" else lb.score_piege_grounding(rep, q),
            "info_absente": 1.0 if c != "info_absente" else lb.score_info_absente(rep, q),
            "citation": lb.score_citations(rep, q.get("citation_attendue", [])),
            "faits": lb.score_faits_presents(rep, q),
        }
        print(f"[{q['id']}] {dt:.0f}s | piège={s['piège']:.2f} "
              f"infoA={s['info_absente']:.2f} cit={s['citation']:.2f} "
              f"faits={s['faits']:.2f}")
        print(f"   {rep[:500]}\n")
        lignes_csv.append({
            "question": q["id"], "ok": res["ok"], "duree_s": round(dt, 2),
            "tokens_out": res.get("usage_out", 0),
            "piege": s["piège"], "info_absente": s["info_absente"],
            "citation": s["citation"], "faits": s["faits"], "texte": rep,
        })

    if lignes_csv:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = lb.RESULTS_DIR / f"benchmark_ollama_{args.modele.replace(':', '_')}_{stamp}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(lignes_csv[0].keys()))
            w.writeheader()
            w.writerows(lignes_csv)
        print(f"CSV exporté : {out}")


if __name__ == "__main__":
    main()