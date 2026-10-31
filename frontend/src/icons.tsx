// 消息头像图标（App 与 MessageRow 共用，避免重复定义）
export const IconSpark = ({ size = 15 }: { size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor"><path d="M12 2l2.35 6.65L21 11l-6.65 2.35L12 20l-2.35-6.65L3 11l6.65-2.35L12 2z" /></svg>
)

export const IconUser = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 12a4.5 4.5 0 1 0-4.5-4.5A4.5 4.5 0 0 0 12 12zm0 2.2c-4.5 0-8.2 2.3-8.2 5.1V21h16.4v-1.7c0-2.8-3.7-5.1-8.2-5.1z" /></svg>
)
