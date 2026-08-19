# PROGRESS.md — AO-BTP Copilot Togo

Fichier de continuité entre sessions. À relire en début de chaque session, à mettre à jour en fin de session.

## Objectif du projet

Outil qui scrape les avis d'appel d'offres BTP/Travaux publiés au Togo, en extrait les
informations clés, puis génère — via un RAG ancré sur le corpus légal togolais des marchés
publics — un résumé, une checklist d'éligibilité sourcée (citation d'article) et un chat Q&A
pour une PME du BTP.

Technologies : Python, Web Scraping (BeautifulSoup/Scrapy), NLP, API OpenAI/Llama, Prompt
Engineering, RAG sur un référentiel documentaire spécifique (réglementation BTP togolaise),
avec de vraies données togolaises, pas du synthétique.

## Principe directeur : MVP = chaîne complète, périmètre resserré

Les 5 couches (scraping → extraction → RAG → LLM → interface) doivent TOUTES être réelles et
fonctionnelles. Le "MVP" réduit le VOLUME traité (ex. filtre Travaux, un seul corpus légal
principal), jamais le nombre de couches. Aucune donnée mockée/simulée à aucun niveau.

## Architecture (rappel)

1. **Ingestion** — scraping des AO Travaux/BTP (requests + BeautifulSoup, pas de Scrapy :
   sites cibles pas assez complexes pour le justifier)
2. **Extraction** — parsing PDF (PyMuPDF) + regex/NLP pour champs structurés
3. **Base de connaissance RAG** — corpus légal togolais, chunking par article, embeddings,
   FAISS local
4. **Application LLM** — résumé, checklist d'éligibilité sourcée, chat Q&A grounded
5. **Interface** — Streamlit (liste AO, fiche détail, chat)

Anti over-engineering assumé : pas d'Airflow, pas de vector DB cloud, pas de LangChain
(appels API directs pour comprendre/maîtriser le mécanisme RAG), pas de fine-tuning, pas de
déploiement cloud complexe (Streamlit Cloud gratuit suffit).

## Sources vérifiées (15/08/2026)

**Scraping AO :**
- `marches-publics-togo.com/consultations` — plateforme neuve (lancée 03/2026), structure HTML
  propre (table sémantique en fallback des cards), filtre serveur via
  `?type_marche=Travaux`. **Limite connue : ~9 consultations au total à date, ~2 en Travaux.**
  Volume faible mais 100% réel — c'est la source primaire.
- `arcop.tg/appels-doffres/` — repli si volume insuffisant. Attention : majoritairement des AMI
  (recrutement de consultants), pas des AO travaux, et pas mis à jour depuis 10/2023. À
  utiliser en complément, pas en source principale.
- `arcop.tg/dossiers-types/` — modèles de DAO (dossiers d'appel d'offres types), utile pour
  enrichir les tests d'extraction même si ce ne sont pas des AO "en cours".

**Corpus légal (RAG) :**
- Source principale retenue : **Recueil des textes de la commande publique, édition 2024
  (ARCOP)** — PDF consolidé unique, plus simple à ingérer qu'une collection de décrets épars.
  URL : `https://arcop.tg/wp-content/uploads/2025/10/RECUEIL-DES-TEXTES-DE-LA-COMMANDE-PUBLIQUE-EDITION-2024-ARCOP-PDF-2.pdf`
- Alternative/complément : Décret n°2022-080 portant Code des Marchés Publics, disponible sur
  `dnccp.gouv.tg/dnccp/reglementation/decret/`.

**Contrainte technique sandbox :** le bash tool de Claude n'a pas accès réseau à ces domaines
(allowlist restreinte à pypi/npm/github etc.). Le code livré ici est écrit et testé contre une
fixture HTML reconstituée à partir du contenu réellement observé sur le site (via outil de
fetch web), mais n'a pas encore tourné contre le site en direct. Première tâche de Broly en
session live : lancer le scraper une fois pour de vrai, ajuster les sélecteurs si besoin
(normal en scraping, pas un échec de conception).

## Journal de sessions

### 15/08 — Cadrage
- Architecture définie, sources vérifiées par recherche web
- Planning établi sur 5 jours (16→20/08), granularité journalière, pas de blocs horaires

### 16/08 (J1) — Ingestion + extraction — **EN COURS / avancée notable**
- [x] Scraping réel validé : marches-publics-togo.com → 9 consultations, 3 BTP (2 étiquette site,
  1 mots-clés), titres complets enrichis via les cards
- [x] scraper ARCOP appels-doffres (constat documenté : échantillon 100% AMI consultants, 0 BTP)
- [x] scraper dossiers-types ARCOP (`arcop.tg/dossiers-types/`) : 22 dossiers réels,
  4 catégories (DP, Travaux, Fournitures/services, autres documents)
- [x] téléchargement des 22 .docx (≈6,9 Mo) et du corpus légal (Recueil ARCOP 2024, 39 Mo)
- [x] module extraction.py : texte (docx via python-docx, pdf via PyMuPDF) + champs structurés
  (objet, montant prévisionnel, garantie, délai, validité offres, date limite, lieu, contact) —
  les placeholders des dossiers-types sont documentés (is_placeholder) et non perdus
- [x] stockage SQLite : consultations.db, dossiers_types.db, extraction.db (documents + champs_extraits)
- [x] tests : 26 passent (pytest), fixtures localisées (consultations, arcop, dossiers-types), sans réseau
- [ ] valider le parsing des pages de détail individuelles des AO (URL detail) si besoin pour extraction PDF
- Décisions techniques : voir section ci-dessous
- Blocages : à documenter en session

### 17/08 (J2) — Corpus RAG — chunking **RÉALISÉ le 18/08**
- [x] Analyse du corpus : le texte extrait (`corpus_legal_texte.txt`) était **dégradé**
  par le désordre du PDF 2 colonnes (126 baisses de numérotation)
- [x] Corrigé à la source : ré-extraction par **blocs triés sur coordonnées**
  (`round(y/12), x`) → 12 baisses seulement (toutes = resets entre textes) ;
  fichier `data/processed/corpus_legal_texte_ordonne.txt`
- [x] Normalisation des glyphes du PDF : ligatures (ﬁ, ﬀ, ﬂ) + apostrophes/guillemets
  courbes → ASCII (sinon motifs et embeddings faussés)
- [x] `src/chunking.py` : `extraire_texte_ordonne`, découpage par article
  (`Article premier/1er/N`, `Art.` géré), nettoyage des artéfacts (en-têtes de page,
  `er`, numéros de page, TITRE/CHAPITRE), attribution documentaire ordinale + motifs
- [x] **647 articles → `data/processed/corpus_chunks.json`** (un chunk = un article)
  répartis en **14 textes** : Directive 01/2022, Loi 2021-033, Décret 2022-080,
  2022-063, 2022-070, 2022-092, 2019-096, 2019-097, 2018-171, 2018-028, Arrêté
  087, Loi 2021-034, Décrets 2022-065 et 2022-066 — 0 « inconnu »
- [x] Tests : `tests/test_chunking.py` (8 tests) et `tests/test_index_rag.py`
  (10 tests) — **44 tests au total, verts**
- [x] **Embeddings + FAISS implémentés** (code) : `src/embeddings.py`
  (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dims, local FR) + `src/index_rag.py`
  (IndexFlatIP, cosinus normalisé, sauvegarde/rechargement `index.faiss`+`meta.json`
  +`config.json`, recherche top-k avec score)
- [x] Chaîne validée de bout en bout sur le **vrai corpus en mock** (647 chunks,
  build + query + reload) — le rang en mock n'est pas sémantique (attendu)
- [x] `pip install sentence-transformers` + 1er build `--backend local` → vrai modèle
  multilingue téléchargé, `data/processed/faiss/` généré (647 chunks, dim 384)
- [x] **Rang sémantique validé sur le réel** : requête « appel d'offres ouvert en une
  étape » → **Directive 01/2022, art. 12 en tête** (score 0.8168) ; « garantie de
  bonne exécution taux » → décret 2022-065 PPP art. 29/28
- [x] Ollama : `qwen3.6:27b` retiré (disque), **`llama3.2:1b` installé** (1.3 GB,
  modèle de génération léger local pour le RAG/features)
- [x] Bug CLI corrigé : `index_rag.py query` suit le backend de `config.json`
  (`resoudre_backend`, auto par défaut) — avant, défaut `mock` (dim 16) plantait
  l'index réel (dim 384) en `AssertionError`
- [x] Tests : `tests/test_chunking.py` (8 tests) + `tests/test_index_rag.py` (12 tests
  dont auto-backend) — **45 tests au total, verts**

### 16/08 (J2-bis) — Benchmark LLM (avancée préparatoire au RAG et au choix de modèle)
- [x] Choix des modèles à challenger validé avec l'utilisateur : **Gemini 3.5 Flash**
  (15 RPM / 1 500 RPD / contexte 1M, vérifié web le 16/08) + **Groq openai/gpt-oss-120b**
  (gratuit, API OpenAI-compatible ; remplace le retiré de Groq deepseek-r1-distill-70b,
  404 vérifié en réel le 17/08)
- [x] Ollama local : prévu mais **section commentée** dans le notebook (utilisateur sur
  data mobile limitée) — activation différée
- [x] SDK installés : `google-genai 2.18.1`, `openai 3.1.0`, `ollama 0.6.2`,
  `python-dotenv 1.2.3`, + jupyter lab / nbformat / nbconvert
- [x] Kernel notebook corrigé : `benchllm` (pointe vers le venv → résout
  `ModuleNotFoundError: openai` dans nbconvert)
- [x] `load_dotenv()` explicite dans le notebook (clés depuis `.env` à la racine)
- [x] Exécution réelle (17/08) : **Groq 7/7 OK** (~1-6 s/req) ; **Gemini bloqué**
  par quota free tier réel = **20 req/jour** (429 RESOURCE_EXHAUSTED, vérifié en
  direct le 17/08 ; variable selon compte) ; indices affichés d'erreur ajoutés ;
  retry 429 (backoff) ajoutée dans `call_model`
- [x] Corpus légal extrait en texte : `data/processed/corpus_legal_texte.txt`
  (829 876 caractères, base du contexte fourni au benchmark)
- [x] Jeu d'évaluation 7 questions : `data/eval/eval_questions.json`
  (articles réels 12, 27, 28, 110-111, 113 du Recueil ; 1 piège de grounding ;
  1 question « info absente » anti-hallucination)
- [x] Noyau `src/llm_benchmark.py` : clients Gemini/Groq/(Ollama), prompts grounded,
  scoring auto (piège / honnêteté / citations / faits) + juge LLM (note 0-5 sur
  Langue / Conformité / Format) + pondération 7 critères → note finale /10
- [x] Notebook `notebooks/benchmark_llm.ipynb` : protocole complet, exécutable en
  **mode trace sans clé** (mock local explicite) ; validé de bout en bout
  (12 cellules exécutées, aucune erreur, notes bornées 0-10)
- [x] `.env.example` versionné (gabarit de clés) ; `.env` réel reste ignoré par Git
- [x] (fait hors notebook le 18/08) `.env` réel rempli (clés Gemini + Groq présentes)

### 18/08 (J3) — Features LLM + benchmark Ollama réel
- [x] **`src/llm_features.py`** : résumé, checklist d'éligibilité sourcée, chat Q&A
  grounded — chaque feature récupère le contexte via l'index FAISS réel puis
  appelle le modèle avec un prompt grounded (système « réponds UNIQUEMENT à partir
  du contexte, cite les articles ») ; génération **injectable** → testable sans réseau
- [x] Taille de sortie bornée (def. 500 tokens) : llama3.2:1b en CPU ≈ 6 s / 120 tokens,
  un résumé k=3 ~128 s (prompt-processing du contexte RAG lourd) — latence à
  documenter côté UI
- [x] **Benchmark Ollama réel** : `scripts/benchmark_ollama_reel.py` (repli léger au
  notebook, export CSV) — exécuté : `llama3.2:1b` répond grounded sur le fond
  (proc/délai/garantie/piège suivis) mais **cite des articles/fausses références**
  (ex. « Décret 2019-1010 » inventé, « Article 1/2 » au lieu de 27) → **cit=0 sur
  toutes les questions attendues**. C'était le handicap pressenti d'un modèle 1B.
- [x] Corrections du scoring (2 bugs + 1 faux positif découverts en réel) :
  - `score_info_absente` ne reconnaissait pas « n'est pas précisé » (honnêteté réelle)
  - `score_piege_grounding` : « non » isolé → faux positif ; « n'est JAMAIS exigée »
    non détecté ; clause négation + travaux redéfinie (`_negation_travaux`)
  - tests dédiés : `tests/test_llm_benchmark_scoring.py` (10 cas réels)
- [x] Tests : **67 au total, verts**
- [x] **Décision produit (18/08)** : modèle par défaut des features = **Groq
  gpt-oss-120b** (citations fiables) ; **Ollama llama3.2:1b en repli** hors-ligne
  (`provider="ollama"`), limites documentées
- [x] Borne de sortie features = 1000 tokens + garde-fou « réponse vide » :
  gpt-oss-120b est un modèle à raisonnement — à max=500 il consommait ses tokens
  en raisonnement et renvoyait un texte vide (usage_out=500, text=""), constaté
  en réel ; erreur claire si ça se reproduit
- [x] Test réel des 3 features avec Groq sur AO-2026-00009 : résumé correct,
  checklist grounded sourcée (tableau À vérifier / Règle / Référence, ex. art. 29
  loi-2021-034), chat avec citations exactes (art. 3 décret 2018-171, tableau des
  seuils) — ~15-65 s/réponse
- [x] Tests : **69 au total, verts**
- [x] **Commit `b9acdf6`** « J3 features LLM : résumé, checklist éligibilité sourcée et
  chat grounded sur le RAG réel » — 6 fichiers, 663 insertions, 69 tests verts
- [ ] (attente quota) ré-essayer Gemini + juge LLM Gemini pour compléter la matrice
- [ ] revue manuelle de l'échantillon (cellule 5 du notebook) et contre-échantillon

### 18/08 (J4) — Interface Streamlit (style DeepSeek, Ollama local uniquement)
- [x] streamlit 1.61.1 installé dans le venv ; skill local développer-avec-streamlit
  chargé (layouts centré, chat-ui, performance/cache)
- [x] Données inspectées : consultations.db (9 AO dont 3 BTP), extraction.db
  (22 documents + 44 champs, placeholders dossiers-types), dossiers_types.db (22)
- [x] `llm_features` : paramètre **`index=`** (rechercher_index, _contexte_requetes,
  resumer_ao, checklist_eligibilite, repondre_question) → l'app charge l'index
  FAISS UNE seule fois (`@st.cache_resource`) au lieu de recharger l'embedder
  par appel — tests : 71 verts
- [x] **Redesign complet de l'interface sur retour utilisateur** (« je veux un truc à
  l'instar de DeepSeek, l'utilisateur vient et pose sa question ») :
  - un seul écran de **chat** (layout centré), un seul champ de saisie en bas
  - **détection automatique de l'intention** : question avec « résumé » → résumé ;
  « checklist »/« éligibilité » → checklist sourcée ; sinon → chat Q&A grounded
  - barre latérale minimale : marché concerné (ou corpus entier) + nouvelle discussion
  - **Ollama local UNIQUEMENT** (`llama3.2:1b`) — plus aucun autre modèle dans l'app
    (décision utilisateur explicite du 18/08, voir log des décisions)
  - bug corrigé : v1 du bouton « Générer » ne faisait rien (incrément de variante
    sans `st.rerun()`) → génération unifiée requête/chat ; suggestions cliquables
    branchées sur le même chemin de génération
  - erreurs Ollama gérées proprement (serveur arrêté / modèle absent → message clair)
- [x] Validations réelles : chat Q&A Ollama (seuils) ≈ 154 s à froid puis grounded ;
  pipeline app complet sur AO-2026-00009 (index 647 chunks + résumé + checklist) ;
  `streamlit run app.py` démarre sans erreur (health 200, page servie) ; 71 tests verts
- [x] **Challenge réel de l'app (18/08, sur demande utilisateur)** :
  - chat Q&A grounded **fonctionne bien** (réponse avec fiche AO-2026-00009 correcte,
    art. cités, date limite) ; piège « décret 2019-1010 » → le modèle ne valide pas
    la fausse référence (mais réponse brouillonne)
  - **résumé & checklist : qualité insuffisante avec llama3.2:1b** — résumé hors-sujet
    puis trop court (« La loi de 2022-065-ppp portant modalités… »), checklist avec
    « les informations ne sont pas réelles », emails/orgs inventés (ENIA-ACC, Loi 90-02,
    Décret 94-117/PMRT). Le mécanisme s'exécute, mais le modèle 1B n'est pas fiable
    pour ces deux tâches génératives
- [x] **Garde-fou anti-hallucination local** : `lf.verifier_references()` — analyse la
  réponse et signale toute référence (décret/loi/arrêté/directive n°…, article N)
  **introuvable dans le corpus ARCOP 2024** (registre construit depuis `meta.json`) ;
  affiché en `st.warning` sous chaque réponse (app.py) ; prompt `_system_grounded`
  durci (« n'invente JAMAIS une référence »). Tests : +4 → **75 tests verts**
- [ ] **décision en attente** : pour un résumé/checklist réellement fiables, installer
  un modèle Ollama local plus fort (ex. qwen2.5:7b ~4,7 Go, gemma3:4b) — OK utilisateur
  requis (contrainte disque/data, il a déjà retiré qwen3.6:27b)
- [x] commit du bloc J4 + Étape A (voir section suivante)

### 19/08 (Étape A) — Scalabilité : service web multi-utilisateur

Décision utilisateur : remplacer l'interface Streamlit par un **service web** moderne ; une
seule entreprise au stade A (« Btma Industries ») avec **plusieurs comptes employés** (email +
mot de passe). Les sources ouest-africaines (Bénin, Côte d'Ivoire, Sénégal SYGMAP, bailleurs
AfDB/UNGM/BM) seront alimentées en Étape B.

- [x] **Backend FastAPI** (`server/`) : `main.py` (routes REST + **SSE** + service de la SPA
  `web/dist`), `db.py` (SQLite `data/processed/app.db` : users / conversations / messages,
  connexions courtes thread-safe, transaction sur la même connexion), `auth.py` (PBKDF2 stdlib
  200k itérations + JWT HS256, exp. 24 h), `schemas.py` (Pydantic v2, EmailStr), `config.py`
- [x] **Chat en streaming (SSE)** : `POST /api/conversations/{id}/messages` → `data: {json}\n\n`
  (aiguillage résumé/checklist/chat ; introduction sans appel modèle si marché absent ;
  sinon génération Ollama `llama3.2:1b` streamée `num_predict=1000`)
- [x] **Frontend React/Vite/Tailwind** (`web/`) : AuthPage (connexion/inscription), Chat à la
  DeepSeek — sidebar conversations + marché, streaming SSE progressif, rendu Markdown,
  avertissements `verifier_references` sous chaque réponse ; `web/dist` servi par FastAPI (SPA
  fallback) ; dev Vite 5173 avec proxy `/api` → 8000
- [x] **E2E backend sur données réelles** : register 201 / doublon 409, login 200 / mauvais mdp
  401, me, 9 consultations, création conversation + renommage, introduction SSE ~0,3 s sans
  Ollama, chat réel **805 fragments en 143 s**, conversation persistée
  `[user, assistant, user, assistant]`, titre auto sur le premier message
- [x] **E2E frontend** : build Vite OK (287 modules), SPA 200 à `/`, routes profondes →
  index.html, `/api/meta` intact à côté
- [x] **Bug réel corrigé (tests utilisateur)** : inscription `422` affichée « [object Object] »
  → traduction des erreurs de validation Pydantic en français dans `api.js` (`messageErreur`)
  + validation par champ dans AuthPage (nom ≥ 2, email valide, mot de passe ≥ 8, blocage avant
  envoi) ; vérifié : corps valide → 201 OK. Doc : Difficulté 16
- [x] **Tests** : `tests/test_server.py` (auth, cycle utilisateur/conversation/messages,
  propriété du renommage, aiguillage prompts via index simulé, historique borné) → **86 verts**
- [x] `requirements.txt` : + fastapi, uvicorn, pyjwt, email-validator ; `pytest.ini` :
  `pythonpath = src server`
- [x] **Pack déploiement en ligne** (`deploy/`) : Dockerfile multi-étapes (build web/dist +
  runtime python:3.12-slim + sentence-transformers/faiss), docker-compose.yml (ollama +
  preload llama3.2:1b + app, volume ./data:/app/data, JWT via env_file), .env.example,
  .dockerignore, README d'exploitation (VPS 2 vCPU/4 Go, transfert des données RAG, HTTPS
  Caddy) — **reste à faire** : provisionner le VPS et lancer `docker compose up -d --build`
- [x] **Choix utilisateur : hébergement gratuit = Oracle Cloud Always Free** (instance ARM
  Ampere A1, 4 OCPU/24 Go RAM, gratuit pour toujours). Wheels `faiss-cpu` aarch64 vérifiées
sur PyPI → Docker Compose fonctionne tel quel sur ARM ; guide Oracle pas à pas ajouté au
   `deploy/README.md` (compte, instance ARM, port 8000 en Security List, Docker) + procédure
   de reconstruction de l'index FAISS sur ARM si nécessaire
- [x] **Oracle Cloud ABANDONNÉ (décision utilisateur 20/08)** : l'inscription/exécution est
   **impossible pour l'emplacement de l'utilisateur** (l'offre Always Free ne couvre pas
   sa région) → nouvelle difficulté documentée (Difficulté 17). Basculé sur **Hugging Face
   Spaces Docker** (CPU basic gratuit, 2 vCPU/16 Go, sans carte bancaire)
- [x] **Pack Hugging Face Spaces** (`deploy/hf/`) : `HF-Dockerfile` (build web/node →
   runtime python:3.12-slim → **Ollama + `llama3.2:1b` EMBARQUÉS dans l'image** au build,
   embedding pré-téléchargé, données RAG copiées, CMD port 7860), `entrypoint.sh`
   (ollama serve en fond → attente API → uvicorn `${PORT:-7860}`), `preparer_space.ps1`
   (assemble `hf-space\` : code src/server/web sans node_modules/dist/__pycache__ +
   `data/processed/{faiss,consultations.db,corpus_chunks.json}` + Dockerfile/entrypoint/
   README/.gitignore), `README.md` (création du Space SDK=Docker, push, secret
   `JWT_SECRET`, limites & dépannage)
- [x] **Assemblage testé** : `preparer_space.ps1` OK → `hf-space\` complet (3,1 Mo de
   données RAG) ; script corrigé (imbrication `src\src` → copie du contenu, exclusion
   `__pycache__`, ASCII pur pour éviter l'apostrophe/encodage en PowerShell 5.1) — **à
   pousser par l'utilisateur** (finaliser sauf 1)
- [x] **REDIRECTION UTILISATEUR (décision 20/08) : démo portfolio sans compte** — « juste
   quiconque peut tester le RAG pour le portfolio » → **pack démo `deploy/hf-demo/`** :
   `demo_app.py` (interface **Gradio**, question libre + liste d'appels d'offres pour
   résumé/checklist, **sans aucune authentification**, réutilise `server.rag` : retrieval
   FAISS + streaming Ollama), `Dockerfile` (sans étage Node, Ollama + `llama3.2:1b` +
   embeddings + données **embarqués**), `entrypoint-demo.sh`, `requirements-demo.txt`
   (requirements-server + gradio 5.50), `preparer_demo.ps1`, `README.md`
- [x] **Démo VALIDÉE en local** : gradio 5.50 installé ; `import demo_app` OK ; question
   réelle → streaming Ollama, réponse 614 car. (~2 min à froid : embedder + modèle +
   génération ; SS-usé ensuite)
- [ ] (plus tard, si volume) Postgres, rate limiting, OAuth, upload de fichiers AO

### 20/08 (J5) — Marge — à venir

## Décisions techniques (log cumulatif)

- Pas de Scrapy → `requests` + `BeautifulSoup` suffisent (sites cibles sans JS lourd,
  pagination/filtrage via query params)
- Parsing ancré sur la balise `<table>` en priorité (plus stable que les classes CSS des
  cards), avec fallback sur les blocs "card" si absente
- SQLite plutôt que Postgres pour le stockage local (volume faible, pas de besoin
  multi-utilisateur à ce stade)
- Chunking RAG par article de loi (pas par taille de texte fixe) pour respecter la structure
  juridique du corpus
- FAISS local, pas de vector DB cloud
- Appels API LLM directs (pas de LangChain) pour garder la maîtrise du mécanisme retrieval →
  prompt → génération
- Benchmark LLM grounded : TOUS les modèles reçoivent le MÊME contexte (extraits du
  corpus) → on isole la qualité modèle, pas celle du retrieval
- Scoring mixte : **juge LLM** (modèle non concurrent) + **échantillon manuel** de
  l'utilisateur (pas de full-auto ni de full-manuel)
- Clés API : jamais commitées ; `.env` ignoré, `.env.example` versionné comme gabarit
- **Interface (décision utilisateur 18/08, SUPERSEDE)** : le produit n'utilisera **que
  Ollama local (`llama3.2:1b`)** — « on n'utilise pas un autre modèle que celui de
  Ollama téléchargé en local ». `PROVIDER_DEFAUT = "ollama"` dans `llm_features.py` ;
  l'app `app.py` ne référence aucun autre modèle. Groq/Gemini restent disponibles dans
  le code (benchmark, comparaison qualité) mais **ne sont plus un défaut produit**.
  Qualité assumée : le 1B cite parfois des articles inexacts (cit=0 au benchmark) —
  compensé par des prompts grounded stricts ; à améliorer (modèle local plus fort)
  si la machine le permet.
- Ollama : **modèle de génération local retenu : `llama3.2:1b`** (1.3 GB, installé le
  18/08/2026) ; `qwen3.6:27b` (17 GB) retiré pour libérer le disque. Section notebook
  benchmark commentée → à activer pour le benchmark réel d'Ollama
- PDF 2 colonnes : **ré-extraction par coordonnées** plutôt qu'utiliser le flux du fichier
  (l'ordre du flux intercale les colonnes → 126 vs 12 baisses de numérotation)
- **Étape A (19/08, décision utilisateur)** : le produit évolue d'une app mono-poste Streamlit
  vers un **service web multi-utilisateur** — une entreprise (« Btma Industries »), plusieurs
  comptes employés (email + mot de passe, JWT). Frontend **React + Vite + Tailwind** (pas de
  Streamlit pour le produit final). RAG toujours 100 % local (Ollama `llama3.2:1b`, index FAISS
  local). Étape B à venir : multipays (Togo+BOAD, Bénin, Côte d'Ivoire, Sénégal) + bailleurs
  (AfDB/UNGM/BM), schéma commun et index RAG par pays
- **SSE plutôt que WebSocket** pour le streaming : un seul sens (la réponse du modèle), plus
  simple, compatible proxy Vite et clients HTTP standards ; format `data: {json}\n\n`
- `app.db` **séparé** des bases d'ingestion (consultations/extraction/dossiers_types) → base
  application remplaçable par Postgres au scale-out sans toucher aux scrapers

## Prochaine session

Le cœur de l'**Étape A** (service web multi-utilisateur) est fonctionnel, testé de bout en
bout, **commité et pushé**. Les packs `deploy/` (VPS), `deploy/hf/` (service complet) et
**`deploy/hf-demo/` (démo portfolio sans compte, validée en local)** sont prêts. Priorités :
1. **DÉPLOIEMENT PORTFOLIO (action utilisateur, ~10 min, web uniquement)** :
   ① créer un compte + Space sur huggingface.co/new-space (SDK = **Docker**, nom =
   `ao-btp-copilot-demo`, CPU basic gratuit) ; ② relancer
   `powershell -ExecutionPolicy Bypass -File deploy\hf-demo\preparer_demo.ps1` ;
   ③ onglet **Files → Upload files** : glisser le **contenu** de `hf-demo-space\`
   (3,1 Mo, le modèle est téléchargé pendant le build par HF) ; ④ attendre le build
   (~15-20 min, Logs) ; ⑤ tester `https://<USER>-ao-btp-copilot-demo.hf.space`
   (question libre, streaming) — **aucun secret requis**
2. Mettre le lien sur le portfolio (avec une capture du chat RAG)
3. (option, plus tard) redéployer le service complet multi-utilisateurs `deploy/hf/`
   (secret `JWT_SECRET` requis) et/ou le pack VPS `deploy/`
4. Décision modèle local plus fort pour résumé/checklist (qwen2.5:7b / gemma3:4b) si
   bande-passante/disque disponibles
5. (Étape B) connecteurs Bénin / Côte d'Ivoire / Sénégal / BOAD / bailleurs + schéma commun
   OCDS-like + index RAG par pays
