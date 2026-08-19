// AO-BTP Copilot — démo RAG 100 % côté navigateur (Hugging Face Static Space)
// Retrieval FAISS (copié côté client) + embeddings + génération llama3.2:1b
// via transformers.js (ONNX, WebGPU avec repli WASM). Aucun serveur.

import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3';

const TJS_DIST = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/dist/';
env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.wasmPaths = TJS_DIST;

const MODELE_EMBEDDING = 'Xenova/paraphrase-multilingual-MiniLM-L12-v2';
const MODELE_LLM = 'onnx-community/Llama-3.2-1B-Instruct-q4f16';
const K = 5;

// --- état global --------------------------------------------------------------
let vectors = null;
let meta = null;
let dim = 0;
let ntot = 0;
let extractor = null;
let generator = null;
let genererIndex = 0; // curseur de streaming

// ---------------------------------------------------------------------------
// Données statiques (index FAISS exporté par scripts/export_demo_web.py)
// ---------------------------------------------------------------------------
async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('GET ' + url + ' -> ' + r.status);
  return r.json();
}

async function chargerActifs() {
  const cfg = await fetchJSON(new URL('assets/config.json', import.meta.url));
  meta = await fetchJSON(new URL('assets/meta.json', import.meta.url));
  dim = cfg.dim;
  ntot = cfg.nb_chunks;
  const b64 = (await (await fetch(new URL('assets/vectors.b64.txt', import.meta.url))).text()).trim();
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  vectors = new Float32Array(bin.buffer);
  if (vectors.length !== ntot * dim) {
    throw new Error('taille des vecteurs incohérente (' + vectors.length + ' != ' + ntot * dim + ')');
  }
}

// ---------------------------------------------------------------------------
// Embedding (mêmes poids que le pipeline Python : pooling mean + L2 normalisé)
// ---------------------------------------------------------------------------
async function embe(netext) {
  if (!extractor) {
    extractor = await pipeline('feature-extraction', MODELE_EMBEDDING, {
      device: 'wasm',
      progress_callback: (p) => {
        if (p.status === 'progress') etatTexte('Embedder : ' + pourcent(p.loaded, p.total) + '…');
      },
    });
  }
  const out = await extractor(netext, { pooling: 'mean', normalize: true });
  return out.data; // Float32Array
}

// ---------------------------------------------------------------------------
// Retrieval top-k par similarité de cosinus (index FlatIP normalisé)
// ---------------------------------------------------------------------------
function topK(q) {
  const scores = new Float32Array(ntot);
  for (let i = 0; i < ntot; i++) {
    let s = 0;
    const o = i * dim;
    for (let j = 0; j < dim; j++) s += q[j] * vectors[o + j];
    scores[i] = s;
  }
  const pos = [];
  for (let i = 0; i < ntot; i++) pos.push(i);
  pos.sort((a, b) => scores[b] - scores[a]);
  return pos.slice(0, K).map((i) => ({ ...meta[i], score: scores[i] }));
}

// ---------------------------------------------------------------------------
// Prompts grounded (réplique de src/llm_features.py)
// ---------------------------------------------------------------------------
const CONSIGNE_SYSTEME =
  'Tu es un assistant spécialisé en marchés publics et commande publique au Togo, ' +
  'pour une PME du BTP. Tu réponds UNIQUEMENT à partir du CONTEXTE fourni (extraits ' +
  'juridiques). Si une information n\'est pas dans le contexte, dis-le explicitement, ' +
  "n'invente rien. N'invente JAMAIS un décret, une loi, un arrêté, un article, un " +
  'montant, un organisme, un contact ou une URL : seule une référence présente dans ' +
  'le CONTEXTE peut être citée, telle quelle. Cite les articles lorsque tu t\'appuies ' +
  'sur eux (ex. « Article 12 »).';

const SYSTEME_CHAT =
  CONSIGNE_SYSTEME +
  '\n\n' +
  "Réponds à la question de l'utilisateur à partir du CONTEXTE fourni (extraits " +
  'juridiques). Cite les articles précis dont tu t\'appuies. Si l\'information ' +
  "manque, réponds honnêtement que le corpus ne la contient pas.";

function formaterContexte(chunks) {
  if (!chunks.length) return '(aucun extrait pertinent trouvé dans le corpus)';
  return chunks
    .map((c) => {
      let src = c.document + ', Article ' + c.article;
      if (c.titre) src += ' — ' + c.titre;
      return '[' + src + ']\n' + c.texte;
    })
    .join('\n\n---\n\n');
}

function construirePrompt(question, contexte) {
  return (
    'CONTEXTE JURIDIQUE (extraits du corpus de la commande publique du Togo) :\n' +
    contexte +
    '\n\nQuestion : ' +
    question
  );
}

// ---------------------------------------------------------------------------
// Génération (llama3.2:1b, WebGPU avec repli WASM) — streaming token à token
// ---------------------------------------------------------------------------
async function detecterWebGPU() {
  try {
    if (!('gpu' in navigator)) return false;
    const adapter = await navigator.gpu.requestAdapter();
    return !!adapter;
  } catch {
    return false;
  }
}

async function chargerGenerateur() {
  const webgpu = await detecterWebGPU();
  const device = webgpu ? 'webgpu' : 'wasm';
  try {
    etatTexte("Chargement du modèle (~1,2 Go la 1re fois)…");
    generator = await pipeline('text-generation', MODELE_LLM, {
      dtype: 'q4f16',
      device,
      progress_callback: (p) => {
        if (p.status === 'progress') etatTexte('Modèle : ' + pourcent(p.loaded, p.total) + '…');
      },
    });
  } catch (e) {
    console.warn('WebGPU indisponible, repli WASM :', e);
    generator = await pipeline('text-generation', MODELE_LLM, {
      dtype: 'q4f16',
      device: 'wasm',
    });
  }
}

function pourcent(loaded, total) {
  if (!total) return '';
  return Math.round((loaded / total) * 100) + '%';
}

async function repondre(question, historique) {
  const qv = await embe(question);
  const hits = topK(qv);
  const contexte = formaterContexte(hits);
  const systeme = SYSTEME_CHAT;
  const user = construirePrompt(question, contexte);
  const roles = [
    { role: 'system', content: systeme },
    ...historique,
    { role: 'user', content: user },
  ];

  if (!generator) await chargerGenerateur();

  etatTexte('Génération…');
  etatClasse('marche');

  let buffer = '';
  genererIndex = 0;

  const out = await generator(roles, {
    max_new_tokens: 700,
    do_sample: true,
    temperature: 0.7,
    top_p: 0.9,
    top_k: 50,
    repetition_penalty: 1.05,
    return_full_text: false,
    callback_function: (beams) => {
      const t = beams[0].text || '';
      if (t.length > genererIndex) {
        buffer += t.slice(genererIndex);
        genererIndex = t.length;
        afficherAssistant(buffer);
      }
    },
  });

  const final = (out && out[0] && out[0].generated_text) || buffer;
  if (final !== buffer) afficherAssistant(final);
  return { texte: final, sources: hits };
}

// ---------------------------------------------------------------------------
// Interface
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function etatTexte(t) { $('etat').textContent = t; }
function etatClasse(c) { $('etat').className = 'etat ' + c; }

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function rendreMarkdown(src) {
  let h = esc(src);
  h = h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  h = h.replace(/\*(.+?)\*/g, '<i>$1</i>');
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  const lignes = h.split('\n');
  let out = '';
  let ul = false;
  let ol = false;
  for (const ligne of lignes) {
    const li = ligne.match(/^\s*[-*]\s+(.*)$/);
    const no = ligne.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (li) { if (!ul) { out += '<ul>'; ul = true; } out += '<li>' + li[1] + '</li>'; continue; }
    if (no) { if (!ol) { out += '<ol>'; ol = true; } out += '<li>' + no[2] + '</li>'; continue; }
    if (ul) { out += '</ul>'; ul = false; }
    if (ol) { out += '</ol>'; ol = false; }
    out += (ligne.trim() === '' ? '<br>' : ligne + '<br>');
  }
  if (ul) out += '</ul>';
  if (ol) out += '</ol>';
  return out;
}

function bulle(role, html) {
  const div = document.createElement('div');
  div.className = 'bulle ' + role;
  if (role === 'assistant') div.innerHTML = html;
  else div.textContent = html;
  return div;
}

let bulleAssistante = null;

function afficherAssistant(texte) {
  const m = $('messages');
  if (!bulleAssistante) {
    bulleAssistante = bulle('assistant', '');
    m.appendChild(bulleAssistante);
  }
  bulleAssistante.innerHTML = rendreMarkdown(texte);
  m.scrollTop = m.scrollHeight;
}

function afficherSources(chunks) {
  const section = $('sources');
  const liste = $('sources-liste');
  liste.innerHTML = '';
  for (const c of chunks) {
    const li = document.createElement('li');
    li.innerHTML =
      '<span class="ref">' + esc(c.document) + ' — Article ' + esc(c.article + '') + '</span>' +
      (c.titre ? ' (' + esc(c.titre) + ')' : '') +
      ' · <span class="score">similarité ' + (c.score * 100).toFixed(1) + '%</span>';
    liste.appendChild(li);
  }
  section.hidden = false;
}

const historique = []; // {role, content} (derniers échanges pour le modèle)

async function envoyer(texte) {
  const m = $('messages');
  m.appendChild(bulle('utilisateur', texte));
  bulleAssistante = null;
  afficherAssistant('');
  $('entree').disabled = true;
  $('envoyer').disabled = true;
  try {
    const { texte: rep, sources } = await repondre(texte, historique);
    historique.push({ role: 'user', content: texte });
    historique.push({ role: 'assistant', content: rep });
    if (historique.length > 12) historique.splice(0, historique.length - 12);
    afficherSources(sources);
    etatTexte('Prêt');
    etatClasse('prêt');
  } catch (e) {
    console.error(e);
    afficherAssistant('Erreur : ' + e.message);
    etatTexte('Erreur : ' + e.message);
    etatClasse('erreur');
  } finally {
    $('entree').disabled = false;
    $('envoyer').disabled = false;
    $('entree').focus();
  }
}

function initialiser() {
  const exemples = [
    "Quelles sont les conditions de participation à un marché de travaux ?",
    "Que doit contenir le dossier de candidature ?",
    "Citer les règles sur les garanties et les avances de démarrage.",
    "Comment se déroule l'évaluation des offres ?",
    "Quelle durée de validité des offres est exigée ?",
  ];
  const box = $('exemples');
  for (const ex of exemples) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = ex;
    b.addEventListener('click', () => { $('entree').value = ex; envoyer(ex); });
    box.appendChild(b);
  }

  $('formulaire').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = $('entree').value.trim();
    if (v) {
      $('entree').value = '';
      envoyer(v);
    }
  });

  chargerActifs()
    .then(() => {
      etatTexte('Index chargé (' + ntot + ' extraits) — chargement de l\'embedder…');
      return embe("bonjour");
    })
    .then(() => {
      etatTexte('Prêt — posez une question.');
      etatClasse('prêt');
      $('entree').disabled = false;
      $('envoyer').disabled = false;
      $('entree').focus();
    })
    .catch((e) => {
      console.error(e);
      etatTexte('Erreur au chargement : ' + e.message);
      etatClasse('erreur');
    });
}

initialiser();