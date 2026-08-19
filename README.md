# AO-BTP Copilot

Assistant **RAG** de suivi des **appels d'offres de marchés publics** pour une
PME du BTP au Togo. Il combine un corpus juridique de la commande publique
(ARCOP 2024), des avis d'appels d'offres réels collectés automatiquement, et un
modèle de langage local (`llama3.2:1b` via Ollama) pour répondre en
**résumé**, **checklist d'éligibilité** et **chat** — avec citations
d'articles et garde-fous anti-hallucination. **100 % local et gratuit**
(retrieval FAISS + embeddings multilingues + génération, zéro API cloud).

## Fonctionnalités

- **Chat RAG en streaming** (SSE) : l'assistant répond en temps réel à partir
  du corpus, en citant les articles utilisés.
- **Aiguillage automatique** des questions vers *résumé d'un appel d'offres*,
  *checklist d'éligibilité sourcée* ou *chat grounded*.
- **Service web multi-utilisateurs** (Étape A) : comptes employés (email +
  mot de passe, JWT), conversations persistées (SQLite).
- **Démo portfolio dans le navigateur** : tout le RAG (index + embeddings +
  modèle) tourne côté client (WebGPU/WASM), sans serveur ni compte.
- Sources fiables : corpus ARCOP, `directive-01-2022-ppp`,
  `code-des-marches-publics-2022`, etc. — 647 extraits indexés.

## Architecture

| Brique | Techno | Détail |
|---|---|---|
| Ingestion (scrapers) | Python, `requests` + BeautifulSoup | Avis d'AO (ARCOP & marchés publics), dossiers-types |
| Extraction PDF | PyMuPDF (coordonnées) | Recueil 2024, découpage par article |
| Embeddings | `sentence-transformers` | `paraphrase-multilingual-MiniLM-L12-v2` (384 d) |
| Index | **FAISS** local (`IndexFlatIP`) | 647 chunks, similarité de cosinus |
| Génération | **Ollama** | `llama3.2:1b` (décision produit : aucun autre modèle) |
| API | **FastAPI** | REST + SSE, auth JWT (PBKDF2 200k itérations) |
| Frontend | **React + Vite + Tailwind** | chat DeepSeek-like, rendu Markdown, avertissements |
| Serveur | uvicorn | sert l'API + `web/dist` (SPA) |
| Tests | pytest | **86 tests verts** |

## Structure

```
src/            scrapers, extraction, embeddings, index_rag, llm_features, benchmark
server/         FastAPI : auth, db, rag, schemas, config, main
web/            frontend React/Vite/Tailwind (Étape A)
deploy/         packaging : VPS (Docker Compose), HF Spaces (service + démo
                Gradio), HF Static (démo WebGPU en navigateur)
scripts/        export_demo_web.py (génère les données de la démo statique)
data/processed/ corpus, index FAISS, consultations, app.db (gitignorés)
tests/          tests serveur (auth, RAG, aiguillage)
Documentation.md  guide complet (choix techniques, difficultés §1–§38)
PROGRESS.md     journal de sessions
```

## Démarrage rapide (local)

```powershell
# 1. Frontend (si l'Étape A est reprise)
cd web; npm install; npm run dev          # Vite sur :5173 (proxy /api → 8000)

# 2. Backend (venv Python)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn server.main:app --reload

# 3. Ollama (modèle de génération local)
ollama pull llama3.2:1b
```

Puis ouvrir http://localhost:5173 — ou la SPA compilée sur http://localhost:8000
(`web/dist` reconstruit avec `npm run build`).

Réindexer le corpus / interroger en CLI :

```powershell
.venv\Scripts\python.exe src/index_rag.py --chunks data/processed/corpus_chunks.json --backend local
.venv\Scripts\python.exe src/index_rag.py --query "conditions de participation" --dir data/processed/faiss -k 5
```

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## Déployer (options)

1. **Démo portfolio « dans le navigateur »** (gratuit pour toujours, sans
   serveur) : `deploy/webgpu-demo/` → nouveau Space Hugging Face en SDK
   **Static**, upload des fichiers, fait. Voir son `README.md`.
2. **Démo Gradio sans compte** (serveur, Ollama embarqué) :
   `deploy/hf-demo/` → Space SDK Docker ; `preparer_demo.ps1` puis upload.
3. **Service complet multi-utilisateurs** : `deploy/hf/` (Space Docker, secret
   `JWT_SECRET`) ou `deploy/` (VPS + Docker Compose). Cf. guides dans chaque
   dossier.

> Note hébergement : depuis juillet 2026, seul le SDK **Static** reste gratuit
> pour tous ; les Spaces Gradio/Docker (même cpu-basic) exigent un abonnement
> Pro. D'où la démo WebGPU statique par défaut.

## Documentation

- `Documentation.md` : architecture, choix techniques (SQLite, chunking par
  article, FAISS, "Ollama uniquement", SSE…), procédures et **38 difficultés
  résolues** (parsing PDF, quotas API, en-codage Windows, déploiement, etc.).
- `PROGRESS.md` : journal de sessions et décisions cumulatives.

---

*Projet personnel d'apprentissage — AO-BTP Copilot.*