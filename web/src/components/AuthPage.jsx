import { useState } from 'react'
import { api } from '../api.js'

function Champ({ label, type, value, onChange, autoFocus = false, messageErreur }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        autoComplete={type === 'password' ? 'current-password' : 'on'}
        className={`w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-slate-100 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/30 ${
          messageErreur ? 'border-red-500/60' : 'border-slate-700'
        }`}
      />
      {messageErreur && (
        <span className="mt-1 block text-xs text-red-400">{messageErreur}</span>
      )}
    </label>
  )
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState('login')
  const [nom, setNom] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [erreur, setErreur] = useState('')
  const [erreursChamps, setErreursChamps] = useState({})
  const [chargement, setChargement] = useState(false)

  function valider() {
    const erreurs = {}
    if (mode === 'register' && nom.trim().length < 2) {
      erreurs.nom = 'Au moins 2 caractères'
    }
    if (!EMAIL.test(email.trim())) {
      erreurs.email = 'Email invalide (ex. jeanne@btma.ci)'
    }
    if (password.length < 8) {
      erreurs.password = 'Au moins 8 caractères'
    }
    setErreursChamps(erreurs)
    return Object.keys(erreurs).length === 0
  }

  async function soumettre(e) {
    e.preventDefault()
    setErreur('')
    if (!valider()) return
    setChargement(true)
    try {
      const rep = mode === 'login'
        ? await api.login({ email: email.trim(), password })
        : await api.register({ nom: nom.trim(), email: email.trim(), password })
      onAuthed(rep.token, rep.user)
    } catch (err) {
      setErreur(err.message)
    } finally {
      setChargement(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f1115] p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 text-2xl font-black text-white shadow-lg shadow-amber-900/40">
            AO
          </div>
          <h1 className="text-2xl font-bold text-white">AO-BTP Copilot</h1>
          <p className="mt-1 text-sm text-slate-400">
            Assistant RAG des marchés publics · <span className="text-slate-200">Btma Industries</span>
          </p>
        </div>

        <form
          onSubmit={soumettre}
          className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl"
        >
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-slate-800/60 p-1">
            {['login', 'register'].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setErreur(''); setErreursChamps({}) }}
                className={`rounded-md py-2 text-sm font-medium transition ${
                  mode === m ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m === 'login' ? 'Connexion' : 'Créer un compte'}
              </button>
            ))}
          </div>

          {mode === 'register' && (
            <div className="mb-4">
              <Champ label="Nom complet" type="text" value={nom} onChange={setNom} autoFocus
                messageErreur={erreursChamps.nom} />
            </div>
          )}
          <div className={mode === 'login' ? '' : 'mb-4'}>
            <Champ label="Email professionnel" type="email" value={email} onChange={setEmail}
              autoFocus={mode === 'login'} messageErreur={erreursChamps.email} />
          </div>
          <div className="mb-5">
            <Champ
              label="Mot de passe (8 caractères min.)"
              type="password"
              value={password}
              onChange={setPassword}
              messageErreur={erreursChamps.password}
            />
          </div>

          {erreur && (
            <p className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {erreur}
            </p>
          )}

          <button
            type="submit"
            disabled={chargement}
            className="w-full rounded-lg bg-amber-500 py-2.5 font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-50"
          >
            {chargement ? 'Un instant…' : mode === 'login' ? 'Se connecter' : 'Créer mon compte'}
          </button>

          {mode === 'register' && (
            <p className="mt-3 text-center text-xs text-slate-500">
              Compte réservé au personnel de Btma Industries.
            </p>
          )}
        </form>
      </div>
    </div>
  )
}