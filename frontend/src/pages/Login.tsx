import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, getToken } from '../api/client'

export default function Login() {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (getToken()) {
    navigate('/dashboard', { replace: true })
    return null
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!password.trim()) return
    setLoading(true)
    setError('')
    try {
      await login(password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-logo">✈</div>
        <h1 className="login-title">TG Forward Bot</h1>
        <p className="login-subtitle">请输入密码</p>
        {error && <div className="alert alert-error">{error}</div>}
        <input
          className="input login-input"
          type="password"
          placeholder="请输入密码"
          value={password}
          onChange={e => setPassword(e.target.value)}
          autoFocus
        />
        <button className="btn btn-primary login-btn" type="submit" disabled={loading}>
          {loading ? '验证中...' : '登录'}
        </button>
      </form>
    </div>
  )
}
