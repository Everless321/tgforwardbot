import { useState, useEffect, useCallback } from 'react'
import { fetchAuthStatus, sendCode, verifyCode, verify2FA, logout, type AuthUser } from '../api/client'

type Step = 'phone' | 'code' | '2fa' | 'done'

function StepIndicator({ step }: { step: Step }) {
  const steps: Step[] = ['phone', 'code', '2fa']
  const labels = ['Phone', 'Code', '2FA']
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
      // not authorized, stay on phone step
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
      setError(e instanceof Error ? e.message : 'Failed to send code')
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
      setError(e instanceof Error ? e.message : 'Invalid code')
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
      setError(e instanceof Error ? e.message : 'Invalid password')
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
      setError(e instanceof Error ? e.message : 'Logout failed')
    } finally {
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div className="page auth-page">
        <div className="auth-card">
          <p className="auth-checking">Checking auth status…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Account</h1>

        {step !== 'done' && <StepIndicator step={step} />}

        {error && <div className="alert alert-error">{error}</div>}

        {step === 'phone' && (
          <div className="auth-form">
            <label className="auth-label">Phone Number</label>
            <input
              className="input auth-input"
              type="tel"
              placeholder="+1234567890"
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
              {loading ? 'Sending…' : 'Send Code'}
            </button>
          </div>
        )}

        {step === 'code' && (
          <div className="auth-form">
            <label className="auth-label">Verification Code</label>
            <p className="auth-hint">Enter the code sent to {phone}</p>
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
              {loading ? 'Verifying…' : 'Verify'}
            </button>
            <button className="btn btn-secondary auth-btn-back" onClick={() => { setStep('phone'); setError(null) }}>
              Back
            </button>
          </div>
        )}

        {step === '2fa' && (
          <div className="auth-form">
            <label className="auth-label">Two-Factor Password</label>
            <p className="auth-hint">Your account has 2FA enabled</p>
            <input
              className="input auth-input"
              type="password"
              placeholder="Enter your password"
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
              {loading ? 'Verifying…' : 'Submit'}
            </button>
          </div>
        )}

        {step === 'done' && user && (
          <div className="auth-success">
            <div className="auth-success-icon">✓</div>
            <h2 className="auth-success-title">Authenticated</h2>
            <div className="auth-user-info">
              <div className="auth-user-row">
                <span className="auth-user-label">Name</span>
                <span className="auth-user-value">{user.first_name}</span>
              </div>
              <div className="auth-user-row">
                <span className="auth-user-label">Phone</span>
                <span className="auth-user-value">{user.phone}</span>
              </div>
              {user.username && (
                <div className="auth-user-row">
                  <span className="auth-user-label">Username</span>
                  <span className="auth-user-value">@{user.username}</span>
                </div>
              )}
            </div>
            <button
              className="btn btn-danger auth-btn"
              onClick={handleLogout}
              disabled={loading}
            >
              {loading ? 'Logging out…' : 'Logout'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
