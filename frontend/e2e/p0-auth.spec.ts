import { expect, test, type Page } from '@playwright/test'

/**
 * P0-9 的 e2e 骨架：账号自助面在**真栈**上的浏览器级结构验证。
 *
 * 覆盖范围要如实说边界：
 *   - 覆盖：路由守卫、注册/登录/退出、主题与起始页偏好的**往返**（前端 → Go → PG → 再登录生效）、
 *     改密码后的口令切换，以及入口探针 `/api/v1/ready` 的两探测键。
 *   - 不覆盖：会话删除的 UI（创建一条真会话要走 chat → LLM，属 P1-4 之后的 e2e），
 *     documents 面（P1-3 的前置是文档真相进 PG），以及任何外观审美判断——本文件是**结构级**。
 *
 * ⚠️ 每条用例都自带登录，不共享会话：Playwright 默认**每条用例一个新 context**，
 * localStorage 里的 `accessToken` 不跨用例存活。第一版按 `describe.serial` 写成"注册一次后面直接用"，
 * 结果就是后面的用例全部停在 `/login`——那种失败长得像"选择器错了"，其实是会话没了。
 *
 * 用户名带时间戳：并发或复跑时撞到同一个用户，失败会表现成"登不上"，排查方向完全错。
 */

const PASSWORD = 'E2eChain2026'
const NEW_PASSWORD = 'E2eChain2027'

/**
 * 注册一个**这一条用例专属**的账号并返回用户名。
 *
 * 为什么不"注册一次、其余用例复用"：`user` 写在模块顶层时，它的生命周期等于 worker 里
 * 这份模块的生命周期。本机一次实跑把这种耦合暴露了——注册用例与被它依赖的登录用例拿到了
 * **两个不同的用户名**（模块被按用例重新求值），于是后面的用例全在"登录一个不存在的人"，
 * 失败长得像选择器错了，其实是账号根本不存在。每条自己注册，慢一秒，换掉整类假信号。
 */
async function freshUser(page: Page): Promise<string> {
  const name = `e2e${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`
  await page.goto('/login')
  await page.getByRole('button', { name: '注册', exact: true }).first().click()
  await page.getByPlaceholder('请输入用户名').fill(name)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: '注册', exact: true }).last().click()
  await expect(page.locator('.rail-user .u')).toHaveText(name, { timeout: 10_000 })
  return name
}

/** 走真表单登录（不是往 localStorage 塞 token）：登录面本身就是要验的东西，绕过去等于没测。 */
async function signIn(page: Page, name: string, password: string = PASSWORD) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(name)
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).last().click()
  await expect(page.locator('.rail-user .u')).toHaveText(name, { timeout: 10_000 })
}

/**
 * 退出用 rail 那个**只有 title** 的图标按钮。
 * `/settings` 上其实有两个"退出登录"（rail 图标 + 账号板块的文字按钮），
 * 按名字点会撞 strict mode——这不是测试的毛病，是那个页面确实把同一动作暴露了两次。
 */
async function signOut(page: Page) {
  await page.goto('/chat')
  await page.getByTitle('退出登录').click()
  await expect(page).toHaveURL(/\/login/)
}

/**
 * 在页面里发带令牌的请求。
 * 用 `page.request` 拿不到登录态——令牌的持有者是前端的 localStorage + `api/http.ts`，
 * 而 `page.request` 是不带这些上下文的另一个客户端。
 */
async function apiGet(page: Page, path: string) {
  return page.evaluate(async (p) => {
    const token = localStorage.getItem('accessToken') || ''
    const resp = await fetch(p, { headers: { Authorization: `Bearer ${token}` } })
    return { status: resp.status, body: await resp.json().catch(() => null) }
  }, path)
}

test.describe('P0 账号自助面', () => {
  test('入口链在跑：go-api 的 /ready 两个探测键都在且都 ok', async ({ request }) => {
    const ready = await request.get('/api/v1/ready')
    expect(ready.status(), '/api/v1/ready 不通说明 go-api(:8080) 没起，先跑 dev.py infra + serve + go-serve').toBe(200)
    const body = await ready.json()
    // 两个键与 detail 文案和 Python 逐字对齐是 X1 的 expect，不是风格问题。
    for (const key of ['database', 'redis']) {
      expect(body.checks, `探针里没有 ${key} 这一格`).toHaveProperty(key)
      expect(body.checks[key].status, `${key} 未通过：${JSON.stringify(body.checks[key])}`).toBe('ok')
      expect(body.checks[key].detail).toBe('connected')
    }
  })

  test('未登录访问受保护路由会被送回登录页', async ({ page }) => {
    await page.goto('/history')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: '登录 ResearchPilot' })).toBeVisible()
  })

  test('注册新用户后落到对话页，侧栏显示用户名，能退出', async ({ page }) => {
    const name = `e2efresh${Date.now().toString(36)}`
    await page.goto('/login')
    await page.getByRole('button', { name: '注册', exact: true }).first().click()
    await page.getByPlaceholder('请输入用户名').fill(name)
    await page.getByPlaceholder('请输入密码').fill(PASSWORD)
    await page.getByRole('button', { name: '注册', exact: true }).last().click()

    await expect(page).toHaveURL(/\/chat/, { timeout: 10_000 })
    await expect(page.locator('.rail-user .u')).toHaveText(name)
    await expect(page.locator('.rail-user .r')).toHaveText('普通用户')

    await signOut(page)
    await signIn(page, name)
  })

  test('退出后用同一口令能重新登录，设置页四个板块都在', async ({ page }) => {
    const name = await freshUser(page)
    await signOut(page)
    await signIn(page, name)

    await page.goto('/settings')
    for (const title of ['账号信息', '外观 · 主题', '偏好设置', '修改密码']) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible()
    }
    await expect(page.locator('.account-name')).toHaveText(name)
    // 普通用户不该看见知识库管理块（它是 require_admin 的面上传）。
    await expect(page.getByRole('heading', { name: '知识库管理' })).toHaveCount(0)
  })

  test('切到深色会写进 html 的 data-theme，并且真的落到 PG', async ({ page }) => {
    await freshUser(page)
    await page.goto('/settings')
    await page.getByRole('button', { name: /深色/ }).click()

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await expect(page.locator('.theme-option.active')).toContainText('深色')

    // 主题没有保存按钮（点一下就 PUT），所以"落库了没"只能再拉一次偏好来证。
    const saved = await apiGet(page, '/api/v1/me/preferences')
    expect(saved.status).toBe(200)
    expect(saved.body?.theme, `偏好读回来的 theme 不是 dark：${JSON.stringify(saved.body)}`).toBe('dark')
  })

  test('起始页偏好保存后，重新登录会落到那一页', async ({ page }) => {
    const name = await freshUser(page)
    await page.goto('/settings')
    await page.selectOption('#prefs-start-view', 'history')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.locator('.toast .toast-text')).toContainText('已保存')

    await signOut(page)
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill(name)
    await page.getByPlaceholder('请输入密码').fill(PASSWORD)
    await page.getByRole('button', { name: '登录', exact: true }).last().click()

    // 这条才是"偏好真的存住了"的证据：start_view 只在登录后跳、刷新不跳（第十二轮定的口径）。
    await expect(page).toHaveURL(/\/history/, { timeout: 10_000 })
  })

  test('会话面经 Go 原生可达，空结果恰好是空数组', async ({ page }) => {
    await freshUser(page)
    await page.goto('/history')

    const resp = await apiGet(page, '/api/v1/sessions')
    expect(resp.status).toBe(200)
    // 空必须是 [] 而不是 null：Go 的 nil 切片会编成 null，前端 .map() 直接炸（第十四轮钉的形状）。
    expect(Array.isArray(resp.body?.sessions), `sessions 不是数组：${JSON.stringify(resp.body)}`).toBe(true)

    const items = page.locator('.list-item')
    if ((await items.count()) === 0) {
      await expect(page.getByText('暂无历史记录')).toBeVisible()
    } else {
      await expect(items.first()).toBeVisible()
    }
  })

  test('改密码：旧口令错要报，改完旧口令失效、新口令可用', async ({ page }) => {
    const name = await freshUser(page)
    await page.goto('/settings')

    await page.locator('#pwd-old').fill('wrongcurrent9')
    await page.locator('#pwd-new').fill(NEW_PASSWORD)
    await page.locator('#pwd-confirm').fill(NEW_PASSWORD)
    await page.getByRole('button', { name: '确认修改' }).click()
    await expect(page.locator('.toast-error .toast-text')).toContainText('修改失败')

    await page.locator('#pwd-old').fill(PASSWORD)
    await page.locator('#pwd-new').fill(NEW_PASSWORD)
    await page.locator('#pwd-confirm').fill(NEW_PASSWORD)
    await page.getByRole('button', { name: '确认修改' }).click()
    await expect(page.locator('.toast-ok .toast-text')).toContainText('密码已修改')

    await signOut(page)
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill(name)
    await page.getByPlaceholder('请输入密码').fill(PASSWORD)
    await page.getByRole('button', { name: '登录', exact: true }).last().click()
    await expect(page).toHaveURL(/\/login/, '旧口令还能登，说明改密码没落库')

    await signIn(page, name, NEW_PASSWORD)
  })

  test('登录失败有反馈而不是静默或 500', async ({ page }) => {
    const name = await freshUser(page)
    await signOut(page)
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill(name)
    await page.getByPlaceholder('请输入密码').fill('nope-nope-12')
    await page.getByRole('button', { name: '登录', exact: true }).last().click()

    await expect(page.locator('.toast-error .toast-text')).toBeVisible({ timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/)
    // 登录面已由 Go 接管，Python 的 slowapi 限流头不会跟过来（台账 C33）——这里只能判"有反馈"，
    // 判不了"被限流"，那一条要等 Go 补上限流再钉。
  })
})
