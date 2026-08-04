import { useState } from 'react'
import { useAuth } from './useAuth'

interface Props {
  auth: ReturnType<typeof useAuth>
  onClose?: () => void
}

export function LoginPage({ auth, onClose }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return
    if (mode === 'login') {
      await auth.login(username.trim(), password)
    } else {
      await auth.register(username.trim(), password)
    }
  }

  const switchMode = () => {
    setMode(mode === 'login' ? 'register' : 'login')
  }

  return (
    <div className="login-page">
      <div className="login-card">
        {onClose && (
          <button className="login-back" onClick={onClose} title="返回聊天">
            ← 返回聊天
          </button>
        )}
        <div className="login-logo">🤖</div>
        <h1 className="login-title">AI 对话助手</h1>
        <p className="login-subtitle">
          {mode === 'login' ? '登录以使用 RAG 和 Agent 功能' : '创建账号开始使用'}
        </p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-field">
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="2-20 个字符"
              autoComplete="username"
              disabled={auth.loading}
            />
          </div>
          <div className="form-field">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'register' ? '至少 6 个字符' : '请输入密码'}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              disabled={auth.loading}
            />
          </div>

          {auth.error && <div className="login-error">⚠️ {auth.error}</div>}

          <button type="submit" className="btn-login" disabled={auth.loading || !username.trim() || !password.trim()}>
            {auth.loading ? '处理中…' : mode === 'login' ? '登录' : '注册'}
          </button>
        </form>

        <div className="login-switch">
          {mode === 'login' ? '还没有账号？' : '已有账号？'}
          <button type="button" onClick={switchMode} disabled={auth.loading}>
            {mode === 'login' ? '去注册' : '去登录'}
          </button>
        </div>

        <div className="login-tip">
          💡 聊天模式无需登录即可使用；RAG 和 Agent 需要登录
        </div>
      </div>
    </div>
  )
}
