# ─── Étape 1 : build du frontend (node) ───────────────────────────────────────
FROM node:20-slim AS web

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ─── Étape 2 : runtime Python (FastAPI) ───────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# curl utile pour le diagnostic d'exploitation
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

# Code application (les données restent dans un volume monté, cf. docker-compose.yml)
COPY src/        src/
COPY server/     server/
COPY app.py      .
COPY --from=web  /app/web/dist  web/dist

# .env.example copié pour le confort ; le vrai .env reste un secret (env_file)
COPY .env.example .env.example

EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]