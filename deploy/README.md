# Déploiement en ligne — VPS + Docker Compose

Le chatbot est conteneurisé en 3 services : **ollama** (modèle `llama3.2:1b`),
**preload** (télécharge le modèle au premier démarrage, puis s'arrête) et **app**
(FastAPI + SPA React, port **8000**).

## Prérequis serveur (recommandé)

- VPS Linux (Debian/Ubuntu), **2 vCPU / 4 Go RAM**, ≥ 10 Go de disque libre.
- Docker + plugin Compose : `sudo apt install docker.io docker-compose-v2` (ou la
  méthode officielle Docker).
- Accès réseau sortant (téléchargement des images, des poids LLM et du modèle
  d'embedding au 1er chat).

## Mise en place (une fois)

```bash
# 1. Récupérer le code
git clone https://github.com/AngeloEngineer/AO-BTP-Copilot.git
cd "AO-BTP Copilot/deploy"

# 2. Déposer les données RAG (index FAISS + avis d'appels d'offres) dans ./data
#    Elles sont exclues du dépôt Git. Depuis ta machine :
#      scp -r "data/processed/faiss" user@<IP>:"AO-BTP Copilot/deploy/data/processed/"
#      scp "data/processed/consultations.db" user@<IP>:"AO-BTP Copilot/deploy/data/processed/"
#    Le dossier ./data doit contenir au minimum : processed/faiss/ et processed/consultations.db
#    (app.db — comptes/conversations — y sera créé automatiquement).

# 3. Configurer les secrets
cp .env.example .env
#    puis remplacer JWT_SECRET par un vrai secret :
#    python -c "import secrets; print(secrets.token_hex(32))"

# 4. Construire et démarrer (1er démarrage ~5-15 min : images + llama3.2:1b)
docker compose up -d --build

# 5. Suivre le téléchargement du modèle (service une-shot)
docker compose logs -f preload        # s'arrête seul quand « success » apparaît
```

## Vérification

```bash
curl http://localhost:8000/api/meta    # → {"entreprise":"Btma Industries",...}
curl -I http://localhost:8000/          # → 200, page web servie
```

Ouvrir **http://<IP-du-VPS>:8000** depuis un navigateur : créer un compte, poser
une question. Le **premier chat** prend quelques minutes (téléchargement du modèle
d'embedding ~470 Mo + chargement des poids), puis les réponses arrivent en
**streaming**.

## Mise à jour du code

```bash
git pull
cd deploy
docker compose up -d --build
```

## HTTPS (recommandé avant usage réel)

Option rapide : **Caddy** en frontal.

```console
./caddy reverse-proxy --from exemple.com --to :8000     # sur le même VPS
```

ou dans `docker-compose.yml`, ajouter un service `caddy` avec les volumes
`./Caddyfile:/etc/caddy/Caddyfile:ro` et `80:80, 443:443` (voir la doc Caddy).
Points à pointer sur le VPS : `A` → IP du serveur (et `AAAA` si IPv6).

## Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `app` redémarre en boucle | index FAISS absent de `./data` | vérifier `deploy/data/processed/faiss/` |
| premier chat très lent | téléchargement de l'embedding (~470 Mo) | attendre ; `docker compose logs -f app` |
| « modèle absent » dans le chat | `preload` n'a pas terminé / modèle incomplet | `docker compose logs preload` puis relancer `docker compose run --rm preload` |
| 422 « créez un compte » | données de formulaire invalides (email, mdp < 8) | l'interface affiche maintenant les erreurs en clair |
| RAM insuffisante (OOM) | 1 Go suffit sans torch, mais embedding + 1B ≈ 2-3 Go | prévoir 4 Go ; passer `depends_on` Ollama seul |