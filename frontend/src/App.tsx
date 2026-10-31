import { useEffect, useRef, useState } from 'react'
import { useChat, type ChatMode } from './useChatStream'
import { MessageRow } from './MessageRow'
import { IconSpark, IconUser } from './icons'
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

// ===== 内联 SVG 图标 =====
const IconPlus = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
)
const IconChat = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" /></svg>
)
const IconDoc = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>
)
const IconSend = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" /></svg>
)
const IconStop = () => (
  <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
)
const IconBook = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
)
const IconUpload = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M17 8l-5-5-5 5" /><path d="M12 3v12" /></svg>
)

// 各模式下的快捷提问
const SUGGESTIONS: Record<ChatMode, string[]> = {
  chat: ['用通俗的语言解释什么是 RAG', '帮我写一段简洁的自我介绍', '把「今天天气不错」翻译成英文'],
  rag: ['总结一下文档的核心内容', '文档里提到了哪些技术栈？', '文档的主要观点是什么？'],
  agent: ['现在几点了？今天是星期几？', '帮我搜索今天的科技新闻', '知识库里讲了什么？'],
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
    deleteKnowledge,
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

  // 自动跟随到底部：用 rAF 合批，且用户手动上滑后不再强行拉回
  const followRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  useEffect(() => {
    if (!followRef.current) return
    const el = scrollRef.current
    if (!el) return
    const raf = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
    return () => cancelAnimationFrame(raf)
  }, [messages])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    followRef.current = nearBottom
    setShowJump(!nearBottom)
  }

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (!el) return
    followRef.current = true
    setShowJump(false)
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

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
    followRef.current = true
    setShowJump(false)
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

  const handleDeleteKnowledge = async (documentId: number, name: string) => {
    if (!confirm(`确定删除文档「${name}」？删除后该文档将不再参与检索。`)) return
    try {
      await deleteKnowledge(documentId)
      setToast(`✅ 已删除 ${name}`)
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
          <div className="brand">
            <div className="brand-logo"><IconSpark size={16} /></div>
            <div className="brand-text">AI 对话助手</div>
          </div>
          <button className="btn-new-chat" onClick={newConversation} disabled={loading}>
            <IconPlus />
            <span>新建对话</span>
          </button>
        </div>
        <div className="conv-list">
          <div className="conv-list-label">历史对话</div>
          {conversations.length === 0 && (
            <div className="conv-empty">
              <div className="conv-empty-icon">💬</div>
              暂无历史对话
            </div>
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
            <span className="knowledge-title"><IconBook /> 知识库</span>
            {loadingKnowledge && <span className="knowledge-loading">加载中…</span>}
          </div>
          <div className="knowledge-list">
            {knowledgeList.length === 0 && !loadingKnowledge && (
              <div className="knowledge-empty">暂无文档，请上传 PDF</div>
            )}
            {knowledgeList.map((doc) => (
              <div key={doc.id} className="knowledge-item">
                <div className="knowledge-item-name" title={doc.name}>{doc.name}</div>
                <div className="knowledge-item-meta">
                  <span>{doc.chunks} 块</span>
                  <span>·</span>
                  <span>{doc.pages} 页</span>
                </div>
                <button
                  className="knowledge-delete"
                  title="删除文档"
                  onClick={() => handleDeleteKnowledge(doc.id, doc.name)}
                >
                  ×
                </button>
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
            <IconUpload />
            <span>{uploading ? '上传中…' : '上传 PDF'}</span>
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
          <div className="header-left">
            <h1>{MODE_LABEL[mode]}模式</h1>
            <div className="header-info">
              {currentConvId !== null ? `会话 #${currentConvId}` : '新会话'}
            </div>
          </div>
          <div className="header-right">
            {auth.isAuthenticated && (
              <div className="user-info">
                <span className="user-avatar"><IconUser /></span>
                <span className="user-name">{auth.user?.username}</span>
                <button className="btn-logout" onClick={auth.logout}>
                  退出
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="chat-messages" ref={scrollRef} onScroll={handleScroll}>
          {messages.length === 0 && (
            <div className="empty-tip">
              <div className="empty-logo"><IconSpark size={30} /></div>
              <h2>你好，{auth.user?.username || '访客'} 👋</h2>
              <p className="empty-desc">
                {mode === 'chat' && '流式对话，逐字输出，支持随时中断'}
                {mode === 'rag' && '基于你上传的文档问答，回答带来源溯源'}
                {mode === 'agent' && '智能体自动调用工具，思考过程全程可见'}
              </p>
              <div className="suggestion-chips">
                {SUGGESTIONS[mode].map((s) => (
                  <button key={s} className="suggestion-chip" onClick={() => !loading && send(s)}>
                    {s}
                  </button>
                ))}
              </div>
              {mode === 'rag' && knowledgeList.length === 0 && (
                <p className="sub warn">💡 RAG 模式请先在左侧「上传 PDF」</p>
              )}
            </div>
          )}

          {messages.map((msg) => (
            <MessageRow
              key={msg.id}
              msg={msg}
              modeLabel={msg.mode ? MODE_LABEL[msg.mode] : undefined}
            />
          ))}
          {showJump && (
            <button className="jump-bottom" onClick={scrollToBottom}>
              回到底部
            </button>
          )}
        </div>

        {/* ===== 底部输入区 + 模式切换 ===== */}
        <div className="chat-bottom">
          <div className="mode-tabs">
            {MODE_TABS.map((tab) => {
              const TabIcon = tab.key === 'chat' ? IconChat : tab.key === 'rag' ? IconDoc : IconSpark
              return (
                <button
                  key={tab.key}
                  className={`mode-tab ${mode === tab.key ? 'active' : ''}`}
                  onClick={() => handleModeChange(tab.key)}
                  disabled={loading}
                  title={tab.desc}
                >
                  <TabIcon />
                  <span className="tab-label">{tab.label}</span>
                  <span className="tab-desc">{tab.desc}</span>
                </button>
              )
            })}
          </div>
          <form className="chat-input" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`[${MODE_LABEL[mode]} 模式] 输入你的问题，Enter 发送，Shift+Enter 换行`}
              rows={1}
              disabled={loading}
            />
            {loading ? (
              <button type="button" className="btn-stop" onClick={stop} title="停止生成">
                <IconStop />
                <span>停止</span>
              </button>
            ) : (
              <button type="submit" className="btn-send" disabled={!input.trim()} title="发送">
                <IconSend />
                <span>发送</span>
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
