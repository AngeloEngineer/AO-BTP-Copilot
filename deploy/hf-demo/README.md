# AO-BTP Copilot — démo RAG (portfolio)

Espace **Hugging Face Spaces** (SDK Docker, CPU gratuit, sans carte bancaire)
qui expose publiquement le moteur RAG — **aucun compte requis** : le visiteur
pose une question directement, l'assistant répond en **streaming** à partir du
corpus de marchés publics (retrieval FAISS local + modèle `llama3.2:1b`
embarqué, Ollama).

Interface : Gradio (question libre + liste d'appels d'offres optionnelle pour
les résumés / checklists d'éligibilité).

## Déployer sans aucun terminal (recommandé)

1. Créer un compte puis l'espace : https://huggingface.co/new-space
   - SDK : **Docker**, nom : `ao-btp-copilot-demo`, Hardware : **CPU basic** (gratuit).
2. Dans l'onglet **Files** de l'espace → *Upload files* → glisser le **contenu**
   du dossier `hf-demo-space\` (généré par `preparer_demo.ps1`). Le build
   démarre seul (~15-20 min : pip + Ollama + modèle 1,3 Go + embeddings).
3. URL : **https://<USER>-ao-btp-copilot-demo.hf.space** — prêt, sans secret à
   configurer.

### Variante git
```powershell
powershell -ExecutionPolicy Bypass -File deploy\hf-demo\preparer_demo.ps1
cd hf-demo-space
git init && git add -A && git commit -m "demo"
git remote add origin https://huggingface.co/spaces/<USER>/ao-btp-copilot-demo
git push --set-upstream origin main
```

## Mise à jour
Relancer `preparer_demo.ps1`, puis re-uploader (ou `git add -A && git
commit && git push`).

## Limites (gratuit, assumées)
- Le Space s'endort après inactivité (~48 h) : le 1er visiteur subit le réveil
  (30-90 s) ; son premier message peut prendre 30-60 s (démarrage du modèle).
- Aucune persistance de conversation (interface de démo).

## Dépannage
| Symptôme | Action |
|---|---|
| Build échoue sur `ollama pull` | relancer le push / téléversement (réseau HF parfois capricieux) |
| « Building… » longtemps | normal (image ~3 Go) ; suivre l'onglet Logs |
| 500 / modèle muet au premier message | démarrage à froid : réessayer dans ~30 s |
| Question « résumé/checklist » sans choix | sélectionner un appel d'offres dans la liste déroulante |