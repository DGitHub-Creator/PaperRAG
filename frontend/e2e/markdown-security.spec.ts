import { expect, test } from '@playwright/test'

// 只需真实浏览器和 Vite，不依赖账号、数据库或模型密钥。
for (const source of [
  '<img src=x onerror="window.__injected=true">',
  '<svg onload="window.__injected=true"></svg>',
  '[click](javascript:alert(1))',
  '<script>window.__injected=true</script>',
  '$<img src=x onerror="window.__injected=true">$',
]) {
  test(`净化不可信输出: ${source.slice(0, 35)}`, async ({ page }) => {
    await page.goto('/login')
    const html = await page.evaluate(async (text) => {
      // Vite 直接加载项目源文件，确保测的是实际渲染函数。
      const modulePath = '/src/utils/markdown.ts'
      const { parseMarkdown } = await import(/* @vite-ignore */ modulePath)
      return parseMarkdown(text) as string
    }, source)
    const fragment = await page.evaluate((html) => {
      const root = document.createElement('div')
      root.innerHTML = html
      return {
        dangerous: root.querySelectorAll('script, [onerror], [onload], a[href^="javascript:"]').length,
      }
    }, html)
    expect(fragment.dangerous).toBe(0)
  })
}

test('保留 Markdown、语法高亮和公式', async ({ page }) => {
  await page.goto('/login')
  const html = await page.evaluate(async () => {
    const modulePath = '/src/utils/markdown.ts'
    const { parseMarkdown } = await import(/* @vite-ignore */ modulePath)
    return parseMarkdown('**bold**\n\n```python\nprint(1)\n```\n\n$x^2$\n\n$$y=1$$') as string
  })
  expect(html).toContain('<strong>bold</strong>')
  expect(html).toContain('hljs-built_in')
  expect(html).toContain('katex')
  expect(html).toContain('katex-display')
})
