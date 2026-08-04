import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// 注：移除 StrictMode，避免开发模式下双发请求导致流式接口 ERR_ABORTED
createRoot(document.getElementById('root')!).render(<App />)
