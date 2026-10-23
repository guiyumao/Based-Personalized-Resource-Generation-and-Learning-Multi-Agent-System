import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

const root = resolve(import.meta.dirname, '..')
const componentPath = resolve(root, 'src/components/WeeklyActivityChart.vue')
const outFile = resolve(root, 'output/weekly-activity-preview.html')

const days = (values) => values.map((minutes, index) => ({
  date: `2026-10-${String(17 + index).padStart(2, '0')}`,
  study_seconds: minutes === null ? null : Math.round(minutes * 60),
  answers: minutes === null ? 0 : Math.round(minutes * 0.8),
}))

const scenarios = {
  current: days([0, 0, 0, 0, 0, 0, 4]),
  varied: days([25, 0, 8, 46, 3, 0, 4]),
  zero: days([0, 0, 0, 0, 0, 0, 0]),
  missing: days([null, null, null, null, null, null, null]),
}

const server = await createServer({ root, server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const { default: WeeklyActivityChart } = await server.ssrLoadModule('/src/components/WeeklyActivityChart.vue')

async function render(props) {
  const app = createSSRApp({ render: () => h(WeeklyActivityChart, props) })
  return (await renderToString(app)).replace(/ data-v-[a-z0-9]+=""/g, '')
}

const rendered = {
  current: await render({ days: scenarios.current }),
  varied: await render({ days: scenarios.varied }),
  zero: await render({ days: scenarios.zero }),
  missing: await render({ days: scenarios.missing }),
  narrow: await render({ days: scenarios.varied }),
}
await server.close()

const sfc = readFileSync(componentPath, 'utf8')
const componentCss = sfc.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] ?? ''
const tokens = readFileSync(resolve(root, 'src/styles.css'), 'utf8').match(/:root \{[\s\S]*?\}/)?.[0] ?? ''

const weekdays = ['周六', '周日', '周一', '周二', '周三', '周四', '周五']
const beforeRows = scenarios.current.map((day, index) => {
  const seconds = day.study_seconds
  const label = seconds === null ? '尚未启用采集' : `${Math.floor(seconds / 60)} 分钟`
  return `<div class="old-row"><time>${day.date.slice(5)}</time><meter min="0" max="${Math.max(60, ...scenarios.current.map(d => d.study_seconds ?? 0))}" value="${seconds ?? 0}"></meter><span>${label}</span></div>`
}).join('')

const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>近七日有效活动 · 图表优化对照</title>
<style>
${tokens}
* { box-sizing: border-box; }
body { margin: 0; padding: 32px; background: var(--bg); color: var(--text); font-family: "MiSans","HarmonyOS Sans SC","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
h1 { font-size: 22px; margin: 0 0 6px; }
.lead { margin: 0 0 24px; color: var(--muted); font-size: 13px; line-height: 1.7; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }
.card { padding: 20px; background: var(--panel); border: 1px solid var(--line); border-radius: 18px; min-width: 0; }
.card > h2 { font-size: 16px; margin: 0 0 4px; }
.tag { display: inline-block; margin: 0 0 16px; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
.tag.bad { background: rgba(239,68,68,.1); color: var(--red); }
.tag.good { background: var(--accent-soft); color: var(--accent-deep); }
h3 { font-size: 16px; margin: 16px 0 10px; }
.old-row { display: flex; align-items: center; gap: 12px; margin: 9px 0; font-size: 12px; color: var(--text); }
.old-row meter { flex: 1; min-width: 20px; }
.old-row span { min-width: 64px; color: var(--muted); }
.note { margin: 10px 0 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
${componentCss}
.foot { margin-top: 22px; padding: 16px 18px; background: var(--surface-muted); border-radius: 14px; }
.foot h2 { font-size: 14px; margin: 0 0 8px; }
.foot ul { margin: 0; padding-left: 18px; color: var(--muted); font-size: 12.5px; line-height: 1.9; }
.foot b { color: var(--text); }
</style>
</head>
<body>
<h1>近七日有效活动 · 图表优化对照</h1>
<p class="lead">同一份数据（10/17–10/23，只有今天 4 分钟）在改造前后的呈现。右侧为真实组件 WeeklyActivityChart 的服务端渲染结果。</p>
<div class="grid">
  <section class="card">
    <h2>改造前</h2>
    <span class="tag bad">原生 meter 进度条</span>
    <h3>近七日有效活动</h3>
    ${beforeRows}
    <p class="note">仅统计学习页面可见、获得焦点且近期有操作的活动；空闲和重复标签页不累计，不回填历史时长。</p>
  </section>
  <section class="card">
    <h2>改造后</h2>
    <span class="tag good">带刻度、基线、摘要的柱状图</span>
    <h3>近七日有效活动</h3>
    ${rendered.current}
    <p class="note">仅统计学习页面可见、获得焦点且近期有操作的活动；空闲和重复标签页不累计，不回填历史时长。</p>
  </section>
</div>
<div class="grid" style="margin-top:20px">
  <section class="card">
    <h2>数据有起伏时</h2>
    <span class="tag good">25 / 0 / 8 / 46 / 3 / 0 / 4 分钟</span>
    ${rendered.varied}
  </section>
  <section class="card">
    <h2>空状态</h2>
    <span class="tag good">全 0 与未采集分开表达</span>
    ${rendered.zero}
    <div style="height:12px"></div>
    ${rendered.missing}
  </section>
</div>
<section class="card" style="margin-top:20px">
  <h2>窄列（约 360px，真实面板在窄屏时的宽度）</h2>
  <span class="tag good">字号不随容器缩放，柱宽自适应</span>
  <div style="max-width:360px">${rendered.narrow}</div>
</section>
<section class="foot">
  <h2>改了什么</h2>
  <ul>
    <li><b>有刻度才可比</b>：加 0 / 中值 / 上限三条参考线与坐标标签，柱高按真实分钟数缩放，4 分钟不再看起来"满格"。</li>
    <li><b>零值不再占一整条空轨道</b>：0 分钟画成基线灰点，七天里有六天没有活动时，视觉重心自然落在唯一有效的一天。</li>
    <li><b>补上时间语义</b>：横轴同时给星期与日期，今天标注"今天"并用实色强调，历史日期半透明。</li>
    <li><b>顶部三行小摘要</b>：近 7 日合计、有活动天数、单日最高，不用再去数字符。</li>
    <li><b>空状态代替空图</b>：全 0 提示"暂无有效活动"，接口返回 null 提示"采集尚未启用"，不再把未知写成 0 分钟。</li>
    <li><b>可访问性</b>：figure/figcaption + role="img" 摘要 + 每根柱 title（时长与作答次数），读屏与悬停都有信息。</li>
  </ul>
</section>
</body>
</html>`

mkdirSync(dirname(outFile), { recursive: true })
writeFileSync(outFile, html, 'utf8')
console.log(`written: ${outFile}`)
