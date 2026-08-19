#!/bin/sh
set -e

# Ollama en arrière-plan (même conteneur)
ollama serve >/var/log/ollama.log 2>&1 &

# Attente de l'API Ollama (timeout ~30 s)
i=0
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -gt 30 ] && break
  sleep 1
done

# Démo Gradio sur le port fourni par Hugging Face (7860)
exec python demo_app.py