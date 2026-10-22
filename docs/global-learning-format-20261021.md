# 全局学习内容格式规范化（2026-10-21）

## 背景

用户在「错题本」「收藏本」看到题干、选项、答案、解析仍以普通文本输出：`$f(x)=\frac{x^2-1}{x-1}$`、
`\begin{cases}...\end{cases}` 原样显示。根因不是渲染器缺失（`utils/renderLearningMarkdown.ts` 早已存在），
而是**各页面各自决定是否渲染**：一部分页面调用 `v-html="renderLearningMarkdown(...)"`，另一部分仍是
`{{ }}` 文本插值；`.learning-markdown` 样式也分散在若干组件里，甚至 `ProfileAnalysisView` 有一份不含 KaTeX
的本地 Markdown 实现。本次把「格式化」收敛成单一入口，并把学习正文的展示全部改为走该入口。

## 规范（唯一入口）

1. **渲染**：`src/components/LearningContent.vue`
   - props：`content`、`inline`（短值：选项/答案/标签）、`tag`（默认 `div`）、`empty`（空值兜底文案）、
     `clampLines`（预览折叠行数，**按渲染结果折叠，不截断公式源码**）。
   - 内部只调用 `renderLearningMarkdown`（`html:false`、KaTeX `trust:false`），不做第二套实现。
2. **样式**：`src/styles.css` 的 `.learning-markdown` / `.learning-content.is-inline` /
   `.learning-content.is-clamped` 一节，是全站唯一样式源；公式统一 `overflow-x:auto`，表格/代码/图片/标题一致。
3. **内容层规则**：任何模型生成或用户录入的学习正文（题干、选项、答案、解析、总结、笔记、报告段落、
   讨论内容）必须用 `LearningContent`，禁止 `{{ }}`。短 UI 文案、按钮、状态、id、计数、日期除外。
4. **渲染器增强**：`$...$` 内单个换行按空格处理（长公式被模型折行时不再退化为源码），空行仍不配对，
   长度 >400 字符不当作公式。

## 本次改动文件

| 区域 | 文件 |
| --- | --- |
| 入口/样式 | `components/LearningContent.vue`（新增）、`styles.css`、`utils/learningMarkdownCore.mjs` |
| 重点页面 | `views/MistakeNotebookView.vue`、`views/student/FavoriteNotebookView.vue` |
| 学生端 | `ExerciseView`、`StudyToolsView`、`ReportView`、`ResourceView`、`KnowledgeBaseView`、`ClassroomView`、`DashboardView`、`ProfileAnalysisView`（删除本地 Markdown 实现）、`TranscriptAnalysisView` |
| 教师端 | `TeacherView.vue` |
| 公共组件 | `CoursewareReader`、`LearningOverviewPanel`、`PlanAdaptationPanel`、`PlanFeedbackPanel`、`TaskFeedbackButton` |
| 测试 | `utils/__tests__/learningMarkdown.spec.ts`、`components/__tests__/LearningContent.spec.ts`、`views/student/__tests__/notebooksFormat.spec.ts`（均新增） |

错题卡片预览由 `(prompt||answer).slice(0,80)` 改为渲染后按 2 行折叠，长公式不再被切断。

## 验证

- `npx tsc -p tsconfig.app.json --noEmit` → 0。
- `npx vitest run` → 4 个文件 21 项通过（含错题本卡片/弹窗、收藏本题干选项答案解析、渲染器 8 项、组件 6 项）。
- `npx vite build` → 0（4.77s）。
- 真实 Chromium（本机 5175 Vite）渲染检查：行内公式、分段函数、选项、块级公式、列表、表格均正确渲染，
  证据 `artifacts/global-format-20261021/format-check.png`（临时检查页已删除）。

## 未做 / 保留

- 未用真实登录账号在 5175 打开 `/student/mistakes`、`/student/favorites` 做端到端点击验收（无可用验收账号）。
- `AssistantPet` 的 RAG 来源摘要仍为纯文本：`sourceSummary()` 先 `slice(0,180)` 再显示，属于截断摘要而非学习正文，
  渲染会切断公式，故保留。
- 通知内容、管理端菜单描述、`ProfileAnalysisView` 的 `section.summary` 徽章为短文本，未改。
- 若干 `<p>` 包裹块级渲染结果（合法 DOM，浏览器不会重排），未全部改写为容器组件，避免无谓改动现有排版。
