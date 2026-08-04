import { useState } from 'react'
import type { AgentStep } from './useChatStream'

interface Props {
  steps: AgentStep[]
  streaming?: boolean
}

const STEP_LABEL: Record<AgentStep['type'], string> = {
  thought: '💭 思考',
  action: '🔧 调用工具',
  observation: '👀 观察结果',
  answer: '✅ 回答',
  error: '❌ 错误',
}

const STEP_COLOR: Record<AgentStep['type'], string> = {
  thought: 'step-thought',
  action: 'step-action',
  observation: 'step-observation',
  answer: 'step-answer',
  error: 'step-error',
}

export function ThinkingPanel({ steps, streaming }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  if (!steps || steps.length === 0) return null

  const hasError = steps.some((s) => s.type === 'error')

  return (
    <div className="thinking-panel">
      <div className="thinking-header" onClick={() => setCollapsed(!collapsed)}>
        <span className="thinking-title">
          {hasError ? '⚠️ 思考过程（含错误）' : '🧠 思考过程'}
          {streaming && <span className="thinking-loading"> · 进行中…</span>}
          <span className="thinking-count">({steps.length} 步)</span>
        </span>
        <span className="thinking-toggle">{collapsed ? '展开 ▸' : '收起 ▾'}</span>
      </div>
      {!collapsed && (
        <div className="thinking-steps">
          {steps.map((step, idx) => (
            <div key={idx} className={`thinking-step ${STEP_COLOR[step.type]}`}>
              <div className="step-label">{STEP_LABEL[step.type]}</div>
              <div className="step-body">
                {step.type === 'action' && (
                  <div className="step-action-detail">
                    <span className="step-tool-name">{step.tool}</span>
                    {step.input && (
                      <code className="step-tool-input">{step.input}</code>
                    )}
                  </div>
                )}
                <div className="step-content">{step.content}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
