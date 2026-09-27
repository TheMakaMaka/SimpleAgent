import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端默认地址；dev server 只做代理，不复制业务逻辑
const BACKEND = process.env.AGENT_BACKEND || 'http://127.0.0.1:8000'

const proxy = Object.fromEntries(
  ['/api', '/decisions', '/profile', '/skills', '/candidates', '/reflect', '/encode', '/run'].map(
    (path) => [
      path,
      {
        target: BACKEND,
        changeOrigin: true,
        // SSE 必须关掉缓冲，否则事件会被攒着一起发，动画就没了
        configure: (proxyServer: any) => {
          proxyServer.on('proxyRes', (proxyRes: any) => {
            proxyRes.headers['cache-control'] = 'no-cache, no-transform'
          })
        },
      },
    ],
  ),
)

export default defineConfig({
  // FastAPI 把构建产物挂载在 /app 下，资源路径必须跟着走
  base: '/app/',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
})
