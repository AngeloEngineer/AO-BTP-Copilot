# AO-BTP Copilot — déploiement Hugging Face Spaces (Docker, gratuit)

Ce dossier est le contenu d'un **Hugging Face Space** (SDK **Docker**, CPU gratuit,
sans carte bancaire). Il embarque tout : l'application FastAPI, le frontend React,
**Ollama + llama3.2:1b**, l'embeddings local et les **données RAG** (index FAISS,
consultations). Aucun re-téléchargement au démarrage du Space.

## 1. Créer le compte et l'espace

1. Compte : https://huggingface.co (email — aucune carte bancaire).
2. Create Space : https://huggingface.co/new-space
   - **SDK : Docker**, nom : `ao-btp-copilot`, visibilité : Public.
   - Hardware : **CPU basic** (gratuit).

## 2. Préparer le dossier Space (sur ta machine)

Depuis ce dépôt (une seule commande) :

```powershell
powershell -ExecutionPolicy Bypass -File deploy\hf\preparer_space.ps1
```

Cela crée `hf-space\` à la racine, avec le code + `data\processed\{faiss, consultations.db, corpus_chunks.json}`.

## 3. Pousser

```powershell
cd hf-space
git init
git add -A
git commit -m "Déploiement initial AO-BTP Copilot"
git remote add origin https://huggingface.co/spaces/<USER>/ao-btp-copilot
git push --set-upstream origin main
```

Hugging Face détecte le push, **build l'image** (~10-20 min : pip, Ollama, modèle
1,3 Go, embeddings) — suivant l'onglet **Logs** de l'espace.

## 4. Secret obligatoire

Space **Settings → Variables and secrets → New secret** :

```
JWT_SECRET=<une longue chaîne aléatoire>
```

Générer : `python -c "import secrets; print(secrets.token_hex(32))"`.
Puis **Restart** de l'espace.

## 5. Utiliser

Ouvrir **https://<USER>-ao-btp-copilot.hf.space** : créer un compte (email + mot de
passe ≥ 8 caractères), poser une question. Les réponses arrivent en **streaming**.

## Limites du plan gratuit (assumées)

- Le Space **s'endort après inactivité** (~48 h) : le 1er visiteur subit le
  réveil (30-90 s).
- **Stockage éphémère** : un rebuild (nouveau push) efface les comptes et
  conversations (`app.db`). Compromis du gratuit — pour un usage continu avec
  comptes persistants : brancher une base Postgres gratuite externe (Neon), à
  faire en option B.

## Mise à jour

Régénérer le dossier puis :

```powershell
cd hf-space
git add -A && git commit -m "maj" && git push
```

## Dépannage

| Symptôme | Action |
|---|---|
| Build échoue sur `ollama pull` | relancer le push (réseau Hugging Face sortant parfois capricieux) |
| l'espace « Building… » longtemps | normal (image ~3 Go) ; suivre Logs |
| 500 au premier message | le modèle d'embedding vient juste d'être sollicité ; réessayer |
| « Authentification requise » au chat | `JWT_SECRET` non défini → Settings → Variables and secrets → Restart |