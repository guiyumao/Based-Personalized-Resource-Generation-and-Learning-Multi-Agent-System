# 全局视频来源与公式排版修复

所有真实视频由 `services/agent_service/app/services/resource_artifacts.py::render_video` 本地合成：来源是所选资源的 title/content（课件正文），不是独立视频模型或外部视频抓取。课件正文的文本生成与视频制作是两个阶段；视频制作阶段不调用模型。`resource_generation._ensure_courseware_video` 的自动课件、AssistantTask resource_video 的单独制作，以及 produce_artifact 的学习工作区视频导出均使用此入口。video_script 是结构化脚本资源，不代表已经制作视频文件。

旧实现 Pillow 绘制纯文本，按30字符切行，导致 LaTeX 源码外露/公式拆断。现在网页和视频共用 learningMarkdownCore.mjs 的 Markdown/KaTeX 解析器，支持 $…$、$$…$$、\(…\)、\[…\]；本地 Chromium 排版、按实际文字行/公式/表格行边界分页，再由 OpenCV 编码为960×600的无声VP8/WebM。无效公式阻断输出；超出画面的不可分内容明确失败。保留冒泡排序已有步骤动画。页面明确标示来源。

render_courseware_frames.mjs 仅读取本地包/字体，阻断浏览器网络请求；不执行资源HTML。运行依赖现有Node.js、web-app/node_modules中的Markdown/KaTeX、workspace/node_modules中的Playwright及其Chromium，中文字体和OpenCV；部署时需要一起准备，缺失会明确失败。公式排版与内容数学正确性审核是不同事项，本轮未自动更改正文或数学结论。

课件视频缓存增加 math-v2 后缀，避免复用旧画面，保留旧文件。运行库备份在 artifacts/video-math-20261021/activation/before.sqlite，无迁移、无正文修改。实际运行环境没有历史ResourceArtifact视频行（只读核对为0）；后续工作区导出也统一使用新生成器。

验证：final/command.log 为12 passed；改动Python的Ruff通过；build-final.log前端build退出0。首次公式测试期望数量误写36，实际11×3=33，已更正；真实长课件发现亚像素分页取整问题，已修复并复验。真实资源236的334个公式、34页离线排版无KaTeX错误，并实际查看画面；preview/frames保留证据。

activation/result.json记录已有229–236八份视频重制、解码验证及本人JWT读取HTTP200/字节一致；仅备份和无活动任务检查后重载8002、8007及Worker，其他服务不动。模型台账155→155。未自动提交、未全站回归；本轮未重新执行三个前端入口的浏览器交互验收。
