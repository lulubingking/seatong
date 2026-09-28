/**
 * 应用入口
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.1.1（main.tsx：挂载 App 与全局 ConfigProvider）
 *
 * 顺序：样式（tokens → Tailwind → base）→ AntD ConfigProvider → App
 * 【注意】样式导入顺序不可调整，见 styles/globals.css 注释
 * ────────────────────────────────────────────────────────────────
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { antdTheme } from './theme/antd'
import './styles/globals.css'

// AntD5 默认使用 dayjs，此处仅需中文语言包
const root = document.getElementById('root')
if (!root) throw new Error('#root 未找到，请检查 index.html')

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ConfigProvider theme={antdTheme} locale={zhCN}>
      {/* AntdApp 提供 message/notification/modal 的静态方法上下文（本项目主要用自研 Toast） */}
      <AntdApp>
        <App />
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
)
