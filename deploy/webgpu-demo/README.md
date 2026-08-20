---
title: AO-BTP Copilot — démo RAG en navigateur
colorFrom: indigo
colorTo: blue
sdk: static
pinned: false
license: mit
short_description: RAG marchés publics Togo — 100 % navigateur
---

# AO-BTP Copilot — démo RAG en navigateur

Démo **100 % côté client** de l'assistant RAG de suivi des marchés publics
(corpus de la commande publique du Togo, ARCOP 2024 + avis d'appels d'offres) :
l'index, les embeddings et le modèle `llama3.2:1b` tournent **dans le
navigateur du visiteur** (transformers.js, WebGPU avec repli WASM). Aucun
serveur, aucune donnée envoyée — gratuit pour toujours sur un Static Space.

- Retrieval : similarité de cosinus sur l'index FAISS exporté (647 extraits,
  384 dimensions) — `assets/vectors.b64.txt` + `assets/meta.json`.
- Génération : `onnx-community/Llama-3.2-1B-Instruct-q4f16` (~1,2 Go,
  téléchargé et mis en cache au premier message ; ~90 Mo pour l'embedder).
- Fidèle au pipeline Python : mêmes prompts grounded, même pooling mean +
  normalisation L2, mêmes articles cités.

## Fichiers

```
index.html  styles.css  app.js   — interface de chat streaming
assets/                          — index + métadonnées + consultations (générés)
README.md                        — ce fichier (carte du Space)
```

## Régénérer les données (dépôt source)

```powershell
.venv\Scripts\python.exe scripts\export_demo_web.py
```

Produit `deploy/webgpu-demo/assets/` depuis `data/processed/faiss/` et
`consultations.db`.

## Déployer (Static Space, gratuit)

1. https://huggingface.co/new-space → SDK **Static**, nom au choix (ex.
   `ao-btp-copilot`), Hardware : aucun requis.
2. Onglet **Files → Upload files** : glisser tout le **contenu** de ce dossier
   (les 4 fichiers + `assets/`). Pas de build, le site est servi tel quel.
3. URL : **https://<USER>-<SPACE>.hf.space** — se charger en ~1 min pour les
   visiteurs disposant de WebGPU (les autres passent en WASM, plus lent).

## Bon à savoir

- 1er message : téléchargement du modèle ~1,2 Go (ensuite mis en cache par le
  navigateur). Prévoir un navigateur récent (Chrome/Edge) pour WebGPU ; sans
  WebGPU la génération reste possible mais plus lente.
- Démo technique : modèle local 1B, vérifier les sources officielles.