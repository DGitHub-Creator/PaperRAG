import { defineConfig, devices } from '@playwright/test'

/**
 * P0-9 的 e2e 配置（判据：`cd frontend && npm run test:e2e`）。
 *
 * 形态要说清：这是**结构级** e2e——断言路由、DOM 存在性、属性与文案，不判像素。
 * 本机取证边界（`docs/WORKLOG.md` 附 A 记过）是无头浏览器视口可能为 0×0 且截图不可用；
 * Playwright 自带视口，这里显式钉 1280×800（与 `10 §设计令牌` 的页宽一致），
 * 截图仍只在失败时留，避免把"有截图"当成"验过外观"。
 *
 * webServer 只管 vite；go-api(:8080) 与 ai-core(:8000) 与中间件由 `dev.py` 起
 * ——Playwright 不负责拉起真栈，所以 spec 的第一条用例会显式探活并把"没起栈"报成可读的错。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1280, height: 800 },
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      /**
       * `E2E_BROWSER_CHANNEL` 不设时用 Playwright 自己下载的 chromium——这是**默认路径**，
       * 也是 CI 与别的机器该走的路径。设成 `chrome` / `msedge` 就改用系统浏览器。
       *
       * 本机这轮 P0-9 的实跑证据走的是 `E2E_BROWSER_CHANNEL=chrome`，原因是 Playwright 的
       * chromium 包两次（镜像与官方 CDN）都只解出 `chrome.dll`、`chrome.exe` 被丢，
       * 现象像杀软拦截新落地的可执行文件。这是**本机环境事实**，不是仓库缺陷，
       * 所以不把它写进默认值：写进去就等于让所有机器都依赖"恰好装了 Chrome"。
       */
      use: {
        ...devices['Desktop Chrome'],
        ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
      },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
