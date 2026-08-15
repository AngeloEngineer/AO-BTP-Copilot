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

### 16/08 (J1) — Ingestion + extraction — **EN COURS**
- [ ] Lancer le scraper en conditions réelles (accès réseau complet, poste de Broly)
- [ ] Ajuster les sélecteurs si la structure réelle diffère de la fixture
- [ ] Croiser avec arcop.tg si < 10 AO Travaux récupérés
- [ ] Parser le détail de chaque AO (page individuelle + PDF si présent)
- [ ] Extraction champs clés (objet, date limite, montant, lots, pièces requises)
- [ ] Stockage SQLite (`data/processed/consultations.db`)
- Décisions techniques : voir section ci-dessous
- Blocages : à documenter en session

### 17/08 (J2) — Corpus RAG — à venir
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

## Prochaine session

Reprendre au Jour 1 : exécuter `src/scraper.py` en conditions réelles, valider/ajuster les
sélecteurs, puis passer à l'extraction PDF si le volume d'AO est suffisant.
