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

### 17/08 (J2) — Corpus RAG — à venir

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
- [ ] (bloquant utilisateur) créer son `.env` avec `GEMINI_API_KEY` / `GROQ_API_KEY`
      puis relancer le notebook en mode réel pour obtenir les notes réelles
- [ ] **attente quota Gemini** : relancer après minuit Pacific (le quota à 20 req/jour
      se réinitialise) pour obtenir les réponses + juge Gemini
- [ ] revue manuelle de l'échantillon (cellule 5 du notebook) et contre-échantillon

### 18/08 (J3) — Features LLM — à venir
### 19/08 (J4) — Interface + rigueur — à venir
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
- Ollama : section commentée dans le notebook (data mobile limitée) ; activation dès
  connexion illimitée

## Prochaine session

Priorité :
1. ⏳ (utilisateur) créer `.env` (copie de `.env.example`) + clés Gemini/Groq
2. Lancer `notebooks/benchmark_llm.ipynb` en mode réel → notes réelles des 7 critères
3. Revue manuelle de l'échantillon (cellule 5) pour valider/contredire les auto-scores
4. Jour 2 (corpus RAG) : chunking du Recueil ARCOP 2024 par article, embeddings,
   FAISS local (texte déjà extrait : 829 876 caractères)
