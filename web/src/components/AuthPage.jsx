import { useEffect, useState } from 'react'
import { api } from '../api.js'

function Champ({ label, type, value, onChange, autoFocus = false }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        autoComplete={type === 'password' ? 'current-password' : 'on'}
        className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-slate-100 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/30"
      />
    </label>
  )
}

export default function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState('login')
  const [nom, setNom] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [erreur, setErreur] = useState('')
  const [chargement, setChargement] = useState(false)

  async function soumettre(e) {
    e.preventDefault()
    setErreur('')
    setChargement(true)
    try {
      const rep = mode === 'login'
        ? await api.login({ email, password })
        : await api.register({ nom, email, password })
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
                onClick={() => { setMode(m); setErreur('') }}
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
              <Champ label="Nom complet" type="text" value={nom} onChange={setNom} autoFocus />
            </div>
          )}
          <div className={mode === 'login' ? '' : 'mb-4'}>
            <Champ label="Email professionnel" type="email" value={email} onChange={setEmail}
              autoFocus={mode === 'login'} />
          </div>
          <div className="mb-5">
            <Champ
              label="Mot de passe"
              type="password"
              value={password}
              onChange={setPassword}
              error={mode === 'register' && password.length > 0 && password.length < 8}
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