import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, streamMessage, getToken } from '../api.js'

function Markdown({ children }) {
  return (
    <div className="md text-[0.95rem] leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

function tempsRelatif(iso) {
  const s = Math.max(1, Math.round((Date.now() - Date.parse(iso)) / 1000))
  if (s < 60) return 'à l’instant'
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`
  return `il y a ${Math.round(s / 86400)} j`
}

function Bulle({ m }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-amber-500 px-4 py-2.5 text-slate-950">
          {m.content}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 text-[11px] font-black text-white">
        AO
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900/70 px-4 py-3">
          {m.erreur ? (
            <p className="text-sm text-red-300">{m.content}</p>
          ) : m.enCours && m.content === '' ? (
            <span className="inline-flex gap-1 text-slate-400">
              <span className="animate-bounce">.</span>
              <span className="animate-bounce [animation-delay:0.15s]">.</span>
              <span className="animate-bounce [animation-delay:0.3s]">.</span>
            </span>
          ) : (
            <Markdown>{m.content}</Markdown>
          )}
          {m.avertissements && m.avertissements.length > 0 && (
            <div className="mt-3 space-y-1 border-t border-red-500/20 pt-2">
              {m.avertissements.map((a, i) => (
                <p key={i} className="text-xs text-amber-300">
                  {a}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const SUGGESTIONS = [
  'Quels sont les seuils de passation des marchés de travaux au Togo ?',
  'Quelles garanties sont exigées pour les marchés de travaux ?',
  'Résumé de ce marché',
  "Checklist d'éligibilité pour ce marché",
]

export default function Chat({ user, onLogout }) {
  const [consultations, setConsultations] = useState([])
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [marche, setMarche] = useState('general')
  const [saisie, setSaisie] = useState('')
  const [enCours, setEnCours] = useState(false)
  const ctrl = useRef(null)
  const finDeListe = useRef(null)

  useEffect(() => {
    api.consultations().then(setConsultations).catch(() => {})
    api.conversations().then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    finDeListe.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function ouvrir(conv) {
    ctrl.current?.abort()
    setActiveId(conv.id)
    api.conversation(conv.id)
      .then((d) => setMessages(d.messages || []))
      .catch(() => setMessages([]))
  }

  async function nouvelle() {
    const conv = await api.createConversation()
    setConversations(await api.conversations())
    ouvrir(conv)
  }

  async function supprimer(id) {
    ctrl.current?.abort()
    await api.deleteConversation(id).catch(() => {})
    if (id === activeId) {
      setActiveId(null)
      setMessages([])
    }
    setConversations(await api.conversations())
  }

  async function envoyer(texte) {
    const contenu = (texte ?? saisie).trim()
    if (!contenu || enCours) return
    setSaisie('')

    let conv = conversations.find((c) => c.id === activeId)
    if (!conv) {
      try {
        conv = await api.createConversation()
        setActiveId(conv.id)
        setConversations(await api.conversations())
      } catch {
        return
      }
    }

    setEnCours(true)
    setMessages((ms) => [...ms, { role: 'user', content: contenu },
                               { role: 'assistant', content: '', enCours: true, avertissements: [] }])
    ctrl.current = new AbortController()

    const evts = {
      delta: (e) =>
        setMessages((ms) => {
          const n = [...ms]
          n[n.length - 1] = { ...n[n.length - 1], content: n[n.length - 1].content + e.content }
          return n
        }),
      warnings: (e) =>
        setMessages((ms) => {
          const n = [...ms]
          n[n.length - 1] = { ...n[n.length - 1], avertissements: e.content }
          return n
        }),
      error: (e) =>
        setMessages((ms) => {
          const n = [...ms]
          n[n.length - 1] = { ...n[n.length - 1], content: e.content, erreur: true, enCours: false }
          return n
        }),
      done: async () => {
        setMessages((ms) => {
          const n = [...ms]
          n[n.length - 1] = { ...n[n.length - 1], enCours: false }
          return n
        })
        setEnCours(false)
        setConversations(await api.conversations().catch(() => []))
      },
    }

    try {
      await streamMessage(conv.id, contenu, marche, (e) => evts[e.type]?.(e), ctrl.current.signal)
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages((ms) => {
          const n = [...ms]
          n[n.length - 1] = {
            ...n[n.length - 1],
            content: `Erreur de communication : ${err.message}`,
            erreur: true,
            enCours: false,
          }
          return n
        })
        setEnCours(false)
      }
    }
  }

  const convTitre = conversations.find((c) => c.id === activeId)?.titre

  return (
    <div className="flex h-screen bg-[#0f1115]">
      {/* ---- Barre latérale ---- */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-[#12151b]">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 text-sm font-black text-white">
            AO
          </div>
          <div>
            <p className="text-sm font-semibold text-white">AO-BTP Copilot</p>
            <p className="text-[11px] text-slate-500">Btma Industries</p>
          </div>
        </div>

        <div className="px-3">
          <button
            onClick={nouvelle}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-amber-500 hover:text-amber-400"
          >
            + Nouvelle discussion
          </button>
        </div>

        <div className="px-3 pt-4">
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Marché concerné
          </label>
          <select
            value={marche}
            onChange={(e) => setMarche(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-sm text-slate-200 outline-none focus:border-amber-500"
          >
            <option value="general">Question générale (corpus entier)</option>
            {consultations.map((c) => (
              <option key={c.reference} value={c.reference}>
                {c.reference} — {(c.titre || '').slice(0, 48)}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-[11px] text-slate-600">
            « résumé » / « checklist » agissent sur le marché sélectionné.
          </p>
        </div>

        <nav className="mt-4 flex-1 space-y-1 overflow-y-auto px-3 pb-3">
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => ouvrir(c)}
              className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 transition ${
                c.id === activeId ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm">{c.titre}</p>
                <p className="text-[11px] text-slate-600">{tempsRelatif(c.updated_at)}</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); supprimer(c.id) }}
                title="Supprimer"
                className="ml-2 shrink-0 rounded p-1 text-slate-600 opacity-0 transition group-hover:opacity-100 hover:text-red-400"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-slate-600">
              Aucune discussion pour l’instant.
            </p>
          )}
        </nav>

        <div className="border-t border-slate-800 px-4 py-3">
          <p className="text-sm text-slate-200">{user.nom}</p>
          <p className="text-[11px] text-slate-500">{user.email}</p>
          <button onClick={onLogout} className="mt-2 text-xs text-slate-500 transition hover:text-red-400">
            Se déconnecter
          </button>
        </div>
      </aside>

      {/* ---- Zone de chat ---- */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-300">
              {convTitre ?? 'Nouvelle discussion'}
            </p>
            <p className="text-[11px] text-slate-600">
              RAG local · Recueil ARCOP 2024 · Ollama llama3.2:1b
            </p>
          </div>
          <span className="hidden rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-400 sm:block">
            {marche === 'general' ? 'Corpus entier' : marche}
          </span>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {messages.length === 0 && (
              <div className="py-10 text-center">
                <h2 className="text-xl font-semibold text-white">
                  Bonjour {user.nom}
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">
                  Demandez un <span className="text-slate-200">résumé</span>, une{' '}
                  <span className="text-slate-200">checklist d’éligibilité</span> ou posez
                  une question sur les marchés publics ouest-africains. Réponses ancrées
                  sur le corpus juridique.
                </p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => envoyer(s)}
                      disabled={enCours}
                      className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-left text-sm text-slate-300 transition hover:border-amber-500/60 hover:text-slate-100 disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <Bulle key={i} m={m} />
            ))}
            <div ref={finDeListe} />
          </div>
        </div>

        <div className="border-t border-slate-800 px-4 py-4 sm:px-8">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2 rounded-2xl border border-slate-700 bg-slate-900 px-3 py-2 focus-within:border-amber-500">
              <textarea
                rows={1}
                value={saisie}
                onChange={(e) => setSaisie(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    envoyer()
                  }
                }}
                placeholder="Posez votre question…"
                disabled={enCours}
                className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-[0.95rem] text-slate-100 outline-none placeholder:text-slate-600 disabled:opacity-60"
              />
              <button
                onClick={() => envoyer()}
                disabled={!saisie.trim() || enCours}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-slate-950 transition hover:bg-amber-400 disabled:opacity-40"
                title="Envoyer"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
            <p className="mt-1.5 text-center text-[11px] text-slate-600">
              {enCours
                ? 'Génération en cours avec le modèle local…'
                : 'Les réponses citent les articles du corpus ; les références douteuses sont signalées.'}
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}