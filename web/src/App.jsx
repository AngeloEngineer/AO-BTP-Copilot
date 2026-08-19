import { useEffect, useState } from 'react'
import { api, clearToken, getToken, setToken } from './api.js'
import AuthPage from './components/AuthPage.jsx'
import Chat from './components/Chat.jsx'

export default function App() {
  const [token, setTokenState] = useState(getToken())
  const [user, setUser] = useState(null)
  const [pret, setPret] = useState(Boolean(getToken()))

  useEffect(() => {
    if (!token) {
      setPret(true)
      return
    }
    api.me()
      .then((u) => setUser(u))
      .catch(() => {
        clearToken()
        setTokenState(null)
      })
      .finally(() => setPret(true))
  }, [token])

  function onAuthed(newToken, newUser) {
    setToken(newToken)
    setTokenState(newToken)
    setUser(newUser)
  }

  function deconnexion() {
    clearToken()
    setTokenState(null)
    setUser(null)
  }

  if (!pret) return null

  if (!token || !user) {
    return <AuthPage onAuthed={onAuthed} />
  }

  return <Chat user={user} onLogout={deconnexion} />
}