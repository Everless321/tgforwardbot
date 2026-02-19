import { useState, useEffect, useCallback } from 'react'
import { fetchAuthStatus, sendCode, verifyCode, verify2FA, logout, type AuthUser } from '../api/client'

type Step = 'phone' | 'code' | '2fa' | 'done'

function StepIndicator({ step }: { step: Step }) {
  const steps: Step[] = ['phone', 'code', '2fa']
  const labels = ['手机号', '验证码', '两步验证']
  const current = steps.indexOf(step)

  return (
    <div className="auth-steps">
      {steps.map((s, i) => (
        <div key={s} className="auth-step-group">
          <div className={`auth-step-circle ${i < current ? 'completed' : i === current ? 'active' : 'pending'}`}>
            {i < current ? '✓' : i + 1}
          </div>
          <span className={`auth-step-label ${i === current ? 'active' : ''}`}>{labels[i]}</span>
          {i < steps.length - 1 && <div className={`auth-step-line ${i < current ? 'completed' : ''}`} />}
        </div>
      ))}
    </div>
  )
}

export default function Account() {
  const [step, setStep] = useState<Step>('phone')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checking, setChecking] = useState(true)

  const checkStatus = useCallback(async () => {
    try {
      const data = await fetchAuthStatus()
      if (data.authorized && data.user) {
        setUser(data.user)
        setStep('done')
      }
    } catch {
      // not authorized
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => { checkStatus() }, [checkStatus])

  const handleSendCode = async () => {
    setError(null)
    setLoading(true)
    try {
      await sendCode(phone)
      setStep('code')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '发送验证码失败')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async () => {
    setError(null)
    setLoading(true)
    try {
      const result = await verifyCode(code)
      if (result.status === '2fa_required') {
        setStep('2fa')
      } else {
        setUser(result.user)
        setStep('done')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '验证码无效')
    } finally {
      setLoading(false)
    }
  }

  const handle2FA = async () => {
    setError(null)
    setLoading(true)
    try {
      const result = await verify2FA(password)
      setUser(result.user)
      setStep('done')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '密码无效')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    setError(null)
    setLoading(true)
    try {
      await logout()
      setUser(null)
      setPhone('')
      setCode('')
      setPassword('')
      setStep('phone')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '退出失败')
    } finally {
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div className="page auth-page">
        <div className="auth-card">
          <p className="auth-checking">检查认证状态…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Telegram 账户</h1>

        {step !== 'done' && <StepIndicator step={step} />}

        {error && <div className="alert alert-error">{error}</div>}

        {step === 'phone' && (
          <div className="auth-form">
            <label className="auth-label">手机号码</label>
            <input
              className="input auth-input"
              type="tel"
              placeholder="+8613800138000"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !loading && phone && handleSendCode()}
              disabled={loading}
            />
            <button
              className="btn btn-primary auth-btn"
              onClick={handleSendCode}
              disabled={loading || !phone.trim()}
            >
              {loading ? '发送中…' : '发送验证码'}
            </button>
          </div>
        )}

        {step === 'code' && (
          <div className="auth-form">
            <label className="auth-label">验证码</label>
            <p className="auth-hint">验证码已发送至 {phone}</p>
            <input
              className="input auth-input auth-input-code"
              type="text"
              inputMode="numeric"
              placeholder="12345"
              maxLength={6}
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
              onKeyDown={e => e.key === 'Enter' && !loading && code && handleVerify()}
              disabled={loading}
            />
            <button
              className="btn btn-primary auth-btn"
              onClick={handleVerify}
              disabled={loading || !code.trim()}
            >
              {loading ? '验证中…' : '验证'}
            </button>
            <button className="btn btn-secondary auth-btn-back" onClick={() => { setStep('phone'); setError(null) }}>
              返回
            </button>
          </div>
        )}

        {step === '2fa' && (
          <div className="auth-form">
            <label className="auth-label">两步验证密码</label>
            <p className="auth-hint">您的账户已开启两步验证</p>
            <input
              className="input auth-input"
              type="password"
              placeholder="请输入两步验证密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !loading && password && handle2FA()}
              disabled={loading}
            />
            <button
              className="btn btn-primary auth-btn"
              onClick={handle2FA}
              disabled={loading || !password.trim()}
            >
              {loading ? '验证中…' : '提交'}
            </button>
          </div>
        )}

        {step === 'done' && user && (
          <div className="auth-success">
            <div className="auth-success-icon">✓</div>
            <h2 className="auth-success-title">已认证</h2>
            <div className="auth-user-info">
              <div className="auth-user-row">
                <span className="auth-user-label">昵称</span>
                <span className="auth-user-value">{user.first_name}</span>
              </div>
              <div className="auth-user-row">
                <span className="auth-user-label">手机号</span>
                <span className="auth-user-value">{user.phone}</span>
              </div>
              {user.username && (
                <div className="auth-user-row">
                  <span className="auth-user-label">用户名</span>
                  <span className="auth-user-value">@{user.username}</span>
                </div>
              )}
            </div>
            <button
              className="btn btn-danger auth-btn"
              onClick={handleLogout}
              disabled={loading}
            >
              {loading ? '退出中…' : '退出登录'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
