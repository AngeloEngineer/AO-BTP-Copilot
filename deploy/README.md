# Déploiement en ligne — VPS + Docker Compose

Le chatbot est conteneurisé en 3 services : **ollama** (modèle `llama3.2:1b`),
**preload** (télécharge le modèle au premier démarrage, puis s'arrête) et **app**
(FastAPI + SPA React, port **8000**).

> ✅ **Arm64 (ARM) supporté** : les images `python:3.12-slim`, `ollama/ollama`,
> `sentence-transformers` et les wheels PyPI `faiss-cpu` (aarch64, cf. 1.15.0) sont
> disponibles pour les instances ARM comme **Oracle Always Free**.

## Prérequis serveur (recommandé)

- VPS Linux (Debian/Ubuntu), **2 vCPU / 4 Go RAM**, ≥ 10 Go de disque libre
  (x86 **ou** ARM).
- Docker + plugin Compose : `sudo apt install docker.io docker-compose-v2` (ou la
  méthode officielle Docker).
- Accès réseau sortant (téléchargement des images, des poids LLM et du modèle
  d'embedding au 1er chat).

## Oracle Cloud Always Free — mise en route (gratuit pour toujours)

1. **Créer le compte** sur https://cloud.oracle.com → « Oracle Cloud Free Tier »
   (carte bancaire demandée **pour la vérification d'identité, sans débit**).
2. **Créer une instance** :
   - Image : **Ubuntu 24.04** (Minimal), **Architecture = ARM** ;
   - Shape : **VM.Standard.A1.Flex** (Ampere), **4 OCPU / 24 Go RAM** (Always Free) ;
   - Boot volume : ~50 Go (inclus dans le quota gratuit ~200 Go) ;
   - Clé SSH : coller ta **clé publique** (sinon en générer une depuis la console).
3. **Ouvrir le port 8000** :
   - VCN → *Security Lists* → *Default Security List* → « Add Ingress Rule » :
     Source `0.0.0.0/0`, protocole **TCP**, destination **8000**.
4. Se connecter :
   ```bash
   ssh -i <ta-cle-privee> ubuntu@<IP-publique>
   ```
   puis installer Docker :
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-buildx docker-compose-v2
   sudo usermod -aG docker $USER
   ```
   déconnexion/reconnexion pour activer le groupe `docker`, puis continuer avec la
   section [Mise en place](#mise-en-place-une-fois).

> **Index FAISS et architecture** : l'index actuel a été construit en local (x86).
> Si `app` échoue à le charger sur ARM (« portability trap » rare), le reconstruire
> sur le serveur en une commande (le conteneur inclut l'embedding local) :
> ```bash
> docker compose run --rm --no-deps app \
>   python src/index_rag.py build \
>     --chunks data/processed/corpus_chunks.json \
>     --dir data/processed/faiss --backend local
> ```
> (nécessite d'avoir transféré aussi `corpus_chunks.json`, voir ci-dessous.)

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
#    Optionnel mais conseillé pour la reconstruction ARM : ajouter processed/corpus_chunks.json

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