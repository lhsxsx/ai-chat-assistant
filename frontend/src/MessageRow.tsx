import { memo, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ThinkingPanel } from './ThinkingPanel'
import { IconSpark, IconUser } from './icons'
import type { Message } from './useChatStream'

// 静态 Markdown：text 不变时 React.memo 直接跳过，不再重复解析
const MarkdownBlock = memo(function MarkdownBlock({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
})

/**
 * 流式回答按最后一个空行切成「已定型段落 + 正在生成的尾巴」。
 * 只有尾巴每帧变化，前面的段落字符串不变，就会被 MarkdownBlock 的 memo 命中，
 * 避免每来一个 token 就把整篇回答重新解析一遍。
 */
function splitStreaming(content: string): { stable: string; tail: string } {
  // 未闭合的代码块里可能有空行，此时不能从块内切分
  const fences = content.match(/```/g)
  let limit = content.length
  if (fences && fences.length % 2 === 1) {
    const openAt = content.lastIndexOf('```')
    limit = openAt > 0 ? openAt : 0
  }
  const idx = content.lastIndexOf('\n\n', limit)
  if (idx === -1) return { stable: '', tail: content }
  return { stable: content.slice(0, idx), tail: content.slice(idx + 2) }
}

interface Props {
  msg: Message
  modeLabel?: string
}

export const MessageRow = memo(function MessageRow({ msg, modeLabel }: Props) {
  const { stable, tail } = useMemo(() => {
    if (msg.role !== 'assistant' || !msg.streaming) {
      return { stable: msg.content, tail: '' }
    }
    return splitStreaming(msg.content)
  }, [msg.role, msg.streaming, msg.content])

  return (
    <div className={`msg-row ${msg.role}`}>
      <div className={`msg-avatar ${msg.role === 'user' ? 'avatar-user' : 'avatar-bot'}`}>
        {msg.role === 'user' ? <IconUser /> : <IconSpark size={17} />}
      </div>
      <div className="msg-main">
        {modeLabel && <div className="msg-mode-tag">{modeLabel}</div>}

        {/* Agent 思考过程折叠面板 */}
        {msg.role === 'assistant' && msg.steps && msg.steps.length > 0 && (
          <ThinkingPanel steps={msg.steps} streaming={msg.streaming} />
        )}

        <div className="msg-bubble">
          {msg.role === 'assistant' ? (
            <div className="msg-content markdown">
              {stable && <MarkdownBlock text={stable} />}
              {tail && <MarkdownBlock text={tail} />}
              {msg.streaming && <span className="cursor">▍</span>}
            </div>
          ) : (
            <div className="msg-content">{msg.content}</div>
          )}
        </div>

        {msg.role === 'assistant' && !msg.streaming && msg.sources && msg.sources.length > 0 && (
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
  )
})
