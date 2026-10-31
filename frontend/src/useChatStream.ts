import { useCallback, useRef, useState } from 'react'

export type ChatMode = 'chat' | 'rag' | 'agent'

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  sources?: string[]
  retrievedCount?: number
  mode?: ChatMode
  // Agent 思考过程步骤
  steps?: AgentStep[]
}

// Agent 思考过程的单个步骤
export interface AgentStep {
  type: 'thought' | 'action' | 'observation' | 'answer' | 'error'
  content: string
  tool?: string  // 仅 action 有
  input?: string // 仅 action 有
}

export interface Conversation {
  id: number
  title: string
  mode: string
  created_at?: string
  updated_at?: string
}

export interface KnowledgeDocument {
  id: number
  name: string
  chunks: number
  pages: number
  created_at?: string
}

interface SSEParsed {
  token?: string
  error?: string
  done?: boolean
  // Agent 事件字段
  type?: string
  content?: string
  tool?: string
  input?: string
  // RAG 来源事件字段
  sources?: string[]
  retrieved_count?: number
}

function parseSSEBuffer(buffer: string): { events: SSEParsed[]; rest: string } {
  const events: SSEParsed[] = []
  const parts = buffer.split(/\n\n/)
  const last = parts.pop() ?? ''
  for (const part of parts) {
    const lines = part.split(/\n/).map((l) => l.trim()).filter(Boolean)
    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (payload === '[DONE]') {
        events.push({ done: true })
        continue
      }
      try {
        const obj = JSON.parse(payload)
        // chat 流：{token: "..."}
        if (obj.token) events.push({ token: obj.token })
        // 通用错误
        if (obj.error) events.push({ error: obj.error })
        // agent 流：{type: "thought|action|observation|answer|done|error", content, tool, input}
        if (obj.type) events.push(obj)
      } catch {
        // 忽略无法解析的事件
      }
    }
  }
  return { events, rest: last }
}

const MODE_ENDPOINT: Record<ChatMode, string> = {
  chat: '/chat/stream',
  rag: '/rag/stream',
  agent: '/agent/stream',
}

// 消息自增 id：用于稳定的 React key，避免会话切换时组件状态错位
let messageSeq = 0
const nextMessageId = () => ++messageSeq

export function useChat(getAuthHeaders?: () => Record<string, string>) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [mode, setMode] = useState<ChatMode>('chat')
  // 会话管理
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConvId, setCurrentConvId] = useState<number | null>(null)
  const [loadingConvList, setLoadingConvList] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // 知识库管理
  const [knowledgeList, setKnowledgeList] = useState<KnowledgeDocument[]>([])
  const [loadingKnowledge, setLoadingKnowledge] = useState(false)

  const updateLastAssistant = useCallback(
    (updater: (last: Message) => Message) => {
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last && last.role === 'assistant') {
          copy[copy.length - 1] = updater(last)
        }
        return copy
      })
    },
    []
  )

  // ===== 流式 token 合批：先写进 ref，每帧只提交一次 state =====
  const pendingTextRef = useRef('')
  const rafRef = useRef<number | null>(null)

  const flushPending = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    const text = pendingTextRef.current
    if (!text) return
    pendingTextRef.current = ''
    updateLastAssistant((last) => ({ ...last, content: last.content + text }))
  }, [updateLastAssistant])

  const appendText = useCallback(
    (text: string) => {
      if (!text) return
      pendingTextRef.current += text
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(() => {
          rafRef.current = null
          const buffered = pendingTextRef.current
          if (!buffered) return
          pendingTextRef.current = ''
          updateLastAssistant((last) => ({ ...last, content: last.content + buffered }))
        })
      }
    },
    [updateLastAssistant]
  )

  // 出错信息：先把缓冲区刷出去，再追加错误文案，保证顺序正确
  const appendError = useCallback(
    (message: string) => {
      flushPending()
      updateLastAssistant((last) => ({
        ...last,
        content: (last.content ? last.content + '\n\n' : '') + `[出错] ${message}`,
      }))
    },
    [flushPending, updateLastAssistant]
  )

  // ===== 会话管理 =====
  const refreshConversations = useCallback(async () => {
    setLoadingConvList(true)
    try {
      const resp = await fetch('/history/conversations', {
        headers: { ...(getAuthHeaders?.() || {}) },
      })
      const data = await resp.json().catch(() => ({ conversations: [] }))
      setConversations(data.conversations || [])
    } finally {
      setLoadingConvList(false)
    }
  }, [getAuthHeaders])

  const createConversation = useCallback(
    async (convMode?: ChatMode): Promise<number | null> => {
      const m = convMode ?? mode
      try {
        const resp = await fetch('/history/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(getAuthHeaders?.() || {}) },
          body: JSON.stringify({ mode: m }),
        })
        const data = await resp.json().catch(() => null)
        if (resp.ok && data?.id) {
          setConversations((prev) => [
            {
              id: data.id,
              title: data.title || '新对话',
              mode: data.mode || m,
              created_at: data.created_at,
              updated_at: data.updated_at,
            },
            ...prev,
          ])
          return data.id as number
        }
      } catch {
        // 忽略
      }
      return null
    },
    [mode, getAuthHeaders]
  )

  const selectConversation = useCallback(
    async (convId: number) => {
      // 切换时若仍在加载，先中止当前请求
      if (loading) {
        abortRef.current?.abort()
      }
      try {
        const resp = await fetch(`/history/conversations/${convId}`, {
          headers: { ...(getAuthHeaders?.() || {}) },
        })
        const data = await resp.json().catch(() => null)
        if (resp.ok && data?.messages) {
          const msgs: Message[] = data.messages.map((m: any) => ({
            id: nextMessageId(),
            role: m.role,
            content: m.content,
            sources: m.sources,
            retrievedCount: m.sources?.length,
          }))
          setMessages(msgs)
          setCurrentConvId(convId)
          // 同步 mode（从会话 mode 推断）
          const conv = conversations.find((c) => c.id === convId)
          if (conv && (conv.mode as ChatMode) !== mode) {
            setMode(conv.mode as ChatMode)
          }
        }
      } catch {
        // 忽略
      }
    },
    [loading, conversations, mode, getAuthHeaders]
  )

  const deleteConversation = useCallback(
    async (convId: number) => {
      try {
        const resp = await fetch(`/history/conversations/${convId}`, {
          method: 'DELETE',
          headers: { ...(getAuthHeaders?.() || {}) },
        })
        if (resp.ok) {
          setConversations((prev) => prev.filter((c) => c.id !== convId))
          if (currentConvId === convId) {
            setMessages([])
            setCurrentConvId(null)
          }
        }
      } catch {
        // 忽略
      }
    },
    [currentConvId, getAuthHeaders]
  )

  const newConversation = useCallback(() => {
    if (loading) {
      abortRef.current?.abort()
    }
    setMessages([])
    setCurrentConvId(null)
  }, [loading])

  // ===== 发送消息 =====
  const sendStream = useCallback(
    async (question: string, convId: number | null, controller: AbortController) => {
      const resp = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(getAuthHeaders?.() || {}) },
        body: JSON.stringify({ question, conversation_id: convId }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`请求失败 ${resp.status} ${detail}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSSEBuffer(buffer)
        buffer = rest
        for (const ev of events) {
          if (ev.token) {
            appendText(ev.token)
          }
          if (ev.error) {
            appendError(ev.error)
          }
        }
      }
    },
    [appendText, appendError, getAuthHeaders]
  )

  // RAG 专用：调用 /rag/stream，先收到来源事件，再逐 token 输出答案
  const sendRagStream = useCallback(
    async (question: string, convId: number | null, controller: AbortController) => {
      const resp = await fetch(MODE_ENDPOINT.rag, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(getAuthHeaders?.() || {}) },
        body: JSON.stringify({ question, conversation_id: convId }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`请求失败 ${resp.status} ${detail}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSSEBuffer(buffer)
        buffer = rest
        for (const ev of events) {
          // 来源事件：先展示引用了哪些文件
          if (ev.type === 'sources') {
            const sources = ev.sources || []
            const retrievedCount = ev.retrieved_count ?? 0
            updateLastAssistant((last) => ({
              ...last,
              sources,
              retrievedCount,
            }))
            continue
          }
          if (ev.token) {
            appendText(ev.token)
          }
          if (ev.error) {
            appendError(ev.error)
          }
        }
      }
    },
    [appendText, appendError, getAuthHeaders]
  )

  // Agent 专用：调用 /agent/stream，消费思考过程事件
  const sendAgentStream = useCallback(
    async (question: string, convId: number | null, controller: AbortController) => {
      const resp = await fetch('/agent/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(getAuthHeaders?.() || {}) },
        body: JSON.stringify({ question, conversation_id: convId }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`请求失败 ${resp.status} ${detail}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      const steps: AgentStep[] = []
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSSEBuffer(buffer)
        buffer = rest
        for (const ev of events) {
          // 忽略 done 标记
          if (ev.done) continue
          // 错误事件
          if (ev.type === 'error' || ev.error) {
            const errMsg = ev.content || ev.error || '未知错误'
            steps.push({ type: 'error', content: errMsg })
            updateLastAssistant((last) => ({
              ...last,
              steps: [...steps],
              content: (last.content ? last.content + '\n\n' : '') + `[出错] ${errMsg}`,
            }))
            continue
          }
          // answer 事件：更新最终回答内容
          if (ev.type === 'answer') {
            updateLastAssistant((last) => ({
              ...last,
              content: ev.content || '',
              steps: [...steps],
            }))
            continue
          }
          // thought / action / observation：加入步骤列表
          if (ev.type === 'thought' || ev.type === 'action' || ev.type === 'observation') {
            steps.push({
              type: ev.type as 'thought' | 'action' | 'observation',
              content: ev.content || '',
              tool: ev.tool,
              input: ev.input,
            })
            updateLastAssistant((last) => ({
              ...last,
              steps: [...steps],
            }))
          }
        }
      }
    },
    [updateLastAssistant, getAuthHeaders]
  )

  const send = useCallback(
    async (question: string) => {
      const text = question.trim()
      if (!text || loading) return

      // 若没有当前会话，先创建一个
      let convId = currentConvId
      if (convId === null) {
        convId = await createConversation(mode)
        setCurrentConvId(convId)
      }

      setMessages((prev) => [
        ...prev,
        { id: nextMessageId(), role: 'user', content: text, mode },
        { id: nextMessageId(), role: 'assistant', content: '', streaming: true, mode },
      ])
      setLoading(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        if (mode === 'chat') {
          await sendStream(text, convId, controller)
        } else if (mode === 'agent') {
          // Agent 模式走 SSE 流式，展示思考过程
          await sendAgentStream(text, convId, controller)
        } else {
          // RAG 模式走 SSE 流式，先拿来源再逐 token 输出
          await sendRagStream(text, convId, controller)
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('aborted')) {
          // 用户主动中止
        } else {
          appendError(msg)
        }
      } finally {
        // 先把 rAF 缓冲里剩余的 token 提交，再结束流式状态
        flushPending()
        updateLastAssistant((last) => ({ ...last, streaming: false }))
        setLoading(false)
        abortRef.current = null
        // 刷新会话列表（标题可能已更新）
        refreshConversations()
      }
    },
    [
      loading,
      mode,
      currentConvId,
      createConversation,
      sendStream,
      sendAgentStream,
      sendRagStream,
      updateLastAssistant,
      appendError,
      flushPending,
      refreshConversations,
    ]
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(() => {
    if (loading) return
    setMessages([])
    setCurrentConvId(null)
  }, [loading])

  const changeMode = useCallback((m: ChatMode) => {
    if (loading) return
    setMode(m)
  }, [loading])

  const uploadPdf = useCallback(async (file: File): Promise<string> => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error('目前仅支持 PDF 文件')
    }
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/upload/', {
        method: 'POST',
        headers: { ...(getAuthHeaders?.() || {}) },
        body: form,
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        throw new Error(data.detail || `上传失败 ${resp.status}`)
      }
      return data.message || `上传成功，共 ${data.chunks_count} 块`
    } finally {
      setUploading(false)
    }
  }, [getAuthHeaders])

  const fetchKnowledgeList = useCallback(async () => {
    setLoadingKnowledge(true)
    try {
      const resp = await fetch('/upload/knowledge', {
        headers: { ...(getAuthHeaders?.() || {}) },
      })
      if (!resp.ok) {
        throw new Error(`获取知识库列表失败: ${resp.status}`)
      }
      const data = await resp.json()
      setKnowledgeList(data.documents || [])
    } catch {
      setKnowledgeList([])
    } finally {
      setLoadingKnowledge(false)
    }
  }, [getAuthHeaders])

  const deleteKnowledge = useCallback(
    async (documentId: number) => {
      const resp = await fetch(`/upload/knowledge/${documentId}`, {
        method: 'DELETE',
        headers: { ...(getAuthHeaders?.() || {}) },
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        throw new Error(data.detail || `删除失败 ${resp.status}`)
      }
      setKnowledgeList((prev) => prev.filter((d) => d.id !== documentId))
    },
    [getAuthHeaders]
  )

  return {
    messages,
    loading,
    uploading,
    mode,
    // 会话
    conversations,
    currentConvId,
    loadingConvList,
    refreshConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    newConversation,
    // 知识库
    knowledgeList,
    loadingKnowledge,
    fetchKnowledgeList,
    deleteKnowledge,
    // 操作
    send,
    stop,
    clear,
    changeMode,
    uploadPdf,
  }
}
