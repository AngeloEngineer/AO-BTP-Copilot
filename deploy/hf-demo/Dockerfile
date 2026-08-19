# ── Démo portfolio : AO-BTP Copilot RAG (Hugging Face Spaces, Docker, CPU gratuit) ──
# Aucune authentification : quiconque a l'URL peut tester le RAG.
# Ollama + llama3.2:1b + embeddings EMBARQUÉS dans l'image (aucun téléchargement au réveil).

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Dépendances Python (FastAPI résiduel inutile ici mais compat, + Gradio)
COPY requirements-server.txt requirements-demo.txt ./
RUN pip install --no-cache-dir -r requirements-demo.txt

# Ollama + modèle de génération EMBARQUÉ dans l'image
RUN set -eux; \
    curl -fsSL https://ollama.com/install.sh | sh; \
    (ollama serve >/dev/null 2>&1 &) ; \
    sleep 12; \
    ollama pull llama3.2:1b; \
    pkill ollama || true

# Embedding multilingue pré-téléchargé (le 1er message ne télécharge rien)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Code application + données RAG (index FAISS, consultations, corpus)
COPY src/            src/
COPY server/         server/
COPY demo_app.py     .
COPY data/processed/ data/processed/

COPY entrypoint-demo.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENV PORT=7860
EXPOSE 7860
CMD ["./entrypoint.sh"]