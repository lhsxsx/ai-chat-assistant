import { useEffect, useRef, useState } from 'react'
import { useChat, type ChatMode } from './useChatStream'
import { ThinkingPanel } from './ThinkingPanel'
import { useAuth } from './useAuth'
import { LoginPage } from './LoginPage'
import './App.css'

const MODE_TABS: { key: ChatMode; label: string; desc: string }[] = [
  { key: 'chat', label: '聊天', desc: '纯对话，流式输出' },
  { key: 'rag', label: 'RAG', desc: '基于上传文档问答' },
  { key: 'agent', label: 'Agent', desc: '智能体，自动调用工具' },
]

const MODE_LABEL: Record<ChatMode, string> = {
  chat: '聊天',
  rag: 'RAG',
  agent: 'Agent',
}

// 格式化会话时间
function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day} 天前`
  return d.toLocaleDateString('zh-CN')
}

function App() {
  const auth = useAuth()
  const {
    messages,
    loading,
    uploading,
    mode,
    conversations,
    currentConvId,
    refreshConversations,
    selectConversation,
    deleteConversation,
    newConversation,
    knowledgeList,
    loadingKnowledge,
    fetchKnowledgeList,
    send,
    stop,
    changeMode,
    uploadPdf,
  } = useChat(auth.authHeaders)
  const [input, setInput] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 初始加载会话列表（登录后）
  useEffect(() => {
    if (auth.isAuthenticated) {
      refreshConversations()
      fetchKnowledgeList()
    }
  }, [refreshConversations, fetchKnowledgeList, auth.isAuthenticated])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  // 切换到需要登录的模式时,若未登录则弹出登录页
  const [showLogin, setShowLogin] = useState(false)
  const [pendingMode, setPendingMode] = useState<ChatMode | null>(null)
  const handleModeChange = (m: ChatMode) => {
    if (loading) return
    if ((m === 'rag' || m === 'agent') && !auth.isAuthenticated) {
      setPendingMode(m)
      setShowLogin(true)
      return
    }
    changeMode(m)
  }

  // 登录成功后关闭登录页,并切到用户想去的模式
  useEffect(() => {
    if (auth.isAuthenticated && showLogin) {
      setShowLogin(false)
      if (pendingMode) {
        changeMode(pendingMode)
        setPendingMode(null)
      }
    }
  }, [auth.isAuthenticated, showLogin, pendingMode, changeMode])

  // 登录页覆盖整个界面
  if (showLogin) {
    return <LoginPage auth={auth} onClose={() => setShowLogin(false)} />
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    send(input)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as React.FormEvent)
    }
  }

  const handleUploadClick = () => {
    // 上传 PDF 也需要登录
    if (!auth.isAuthenticated) {
      setShowLogin(true)
      return
    }
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try {
      const msg = await uploadPdf(file)
      setToast(`✅ ${msg}`)
      fetchKnowledgeList()
    } catch (err) {
      setToast(`❌ ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <div className="app-layout">
      {/* ===== 左侧 Sidebar（仅登录后显示）===== */}
      {auth.isAuthenticated && (
      <aside className="sidebar">
        <div className="sidebar-header">
          <button className="btn-new-chat" onClick={newConversation} disabled={loading}>
            + 新建对话
          </button>
        </div>
        <div className="conv-list">
          {conversations.length === 0 && (
            <div className="conv-empty">暂无历史对话</div>
          )}
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conv-item ${currentConvId === conv.id ? 'active' : ''}`}
              onClick={() => selectConversation(conv.id)}
            >
              <div className="conv-item-main">
                <div className="conv-item-title">{conv.title || '新对话'}</div>
                <div className="conv-item-meta">
                  <span className="conv-mode-tag">{MODE_LABEL[conv.mode as ChatMode] || conv.mode}</span>
                  <span className="conv-time">{formatTime(conv.updated_at || conv.created_at)}</span>
                </div>
              </div>
              <button
                className="conv-delete"
                title="删除"
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirm('确定删除这个对话?')) deleteConversation(conv.id)
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {/* ===== 知识库列表 ===== */}
        <div className="knowledge-section">
          <div className="knowledge-header">
            <span className="knowledge-title">📚 知识库</span>
            {loadingKnowledge && <span className="knowledge-loading">加载中…</span>}
          </div>
          <div className="knowledge-list">
            {knowledgeList.length === 0 && !loadingKnowledge && (
              <div className="knowledge-empty">暂无文档，请上传 PDF</div>
            )}
            {knowledgeList.map((doc, idx) => (
              <div key={idx} className="knowledge-item">
                <div className="knowledge-item-name">{doc.name}</div>
                <div className="knowledge-item-meta">
                  <span>{doc.chunks} 块</span>
                  <span>·</span>
                  <span>{doc.pages} 页</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <button
            className="btn-upload-sidebar"
            onClick={handleUploadClick}
            disabled={uploading}
          >
            {uploading ? '上传中…' : '📤 上传 PDF'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            hidden
          />
        </div>
      </aside>
      )}

      {/* ===== 主区域 ===== */}
      <main className="chat-main">
        <header className="chat-header">
          <h1>AI 对话助手</h1>
          <div className="header-right">
            <div className="header-info">
              {currentConvId !== null ? `会话 #${currentConvId}` : '新会话'} · {MODE_LABEL[mode]} 模式
            </div>
            {auth.isAuthenticated && (
              <div className="user-info">
                <span className="user-name">👤 {auth.user?.username}</span>
                <button className="btn-logout" onClick={auth.logout}>
                  退出
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="chat-messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="empty-tip">
              <p>👋 你好！选择模式后输入问题开始对话</p>
              <p className="sub">
                聊天：流式对话 · RAG：基于上传文档问答 · Agent：智能体自动调用工具
              </p>
              <p className="sub">💡 左侧可查看历史记录，点击「新建对话」开始</p>
              {mode === 'rag' && (
                <p className="sub warn">💡 RAG 模式请先点击左下角「上传 PDF」</p>
              )}
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`msg-row ${msg.role}`}>
              <div className="msg-avatar">{msg.role === 'user' ? '🧑' : '🤖'}</div>
              <div className="msg-main">
                {msg.mode && <div className="msg-mode-tag">{MODE_LABEL[msg.mode]}</div>}
                {/* Agent 思考过程折叠面板 */}
                {msg.role === 'assistant' &&
                  msg.steps &&
                  msg.steps.length > 0 && (
                    <ThinkingPanel steps={msg.steps} streaming={msg.streaming} />
                  )}
                <div className="msg-bubble">
                  <div className="msg-content">
                    {msg.content}
                    {msg.streaming && <span className="cursor">▍</span>}
                  </div>
                </div>
                {msg.role === 'assistant' &&
                  !msg.streaming &&
                  msg.sources &&
                  msg.sources.length > 0 && (
                    <div className="msg-sources">
                      <span className="sources-title">📎 引用来源（{msg.retrievedCount} 块）:</span>
                      <ul>
                        {msg.sources.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            </div>
          ))}
        </div>

        {/* ===== 底部输入区 + 模式切换 ===== */}
        <div className="chat-bottom">
          <div className="mode-tabs">
            {MODE_TABS.map((tab) => (
              <button
                key={tab.key}
                className={`mode-tab ${mode === tab.key ? 'active' : ''}`}
                onClick={() => handleModeChange(tab.key)}
                disabled={loading}
                title={tab.desc}
              >
                <span className="tab-label">{tab.label}</span>
                <span className="tab-desc">{tab.desc}</span>
              </button>
            ))}
          </div>
          <form className="chat-input" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`[${MODE_LABEL[mode]} 模式] 输入你的问题…`}
              rows={1}
              disabled={loading}
            />
            {loading ? (
              <button type="button" className="btn-stop" onClick={stop}>
                停止
              </button>
            ) : (
              <button type="submit" className="btn-send" disabled={!input.trim()}>
                发送
              </button>
            )}
          </form>
        </div>
      </main>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

export default App
