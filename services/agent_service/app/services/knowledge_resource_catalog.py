"""Official external learning resources that can be safely linked from the knowledge base."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalKnowledgeResource:
    """One official textbook or courseware resource linked from the knowledge base."""

    title: str
    provider: str
    url: str
    kind: str
    license: str
    notes: str


RESOURCE_CATALOG: dict[str, list[ExternalKnowledgeResource]] = {
    "Python 循环": [
        ExternalKnowledgeResource(
            title="Think Python 2e PDF",
            provider="Green Tea Press",
            url="https://greenteapress.com/thinkpython2/thinkpython2.pdf",
            kind="textbook",
            license="CC BY-NC 3.0",
            notes="官方免费教材，适合 Python 基础、循环与条件判断入门。",
        ),
        ExternalKnowledgeResource(
            title="Think Python 2e HTML",
            provider="Green Tea Press",
            url="https://greenteapress.com/thinkpython2/html/index.html",
            kind="textbook",
            license="CC BY-NC 3.0",
            notes="官方 HTML 版本，便于按章节快速查阅示例。",
        ),
        ExternalKnowledgeResource(
            title="Python 官方教程（中文）",
            provider="Python.org",
            url="https://docs.python.org/zh-cn/3/tutorial/",
            kind="textbook",
            license="PSF License",
            notes="Python 官方中文教程，权威且持续更新，涵盖控制流、循环和基础语法。",
        ),
        ExternalKnowledgeResource(
            title="廖雪峰 Python 教程",
            provider="廖雪峰",
            url="https://www.liaoxuefeng.com/wiki/1016959663602400",
            kind="textbook",
            license="免费在线访问",
            notes="国内流行的中文 Python 教程，语言通俗易懂，适合初学者。",
        ),
        ExternalKnowledgeResource(
            title="菜鸟教程 - Python 循环",
            provider="菜鸟教程",
            url="https://www.runoob.com/python/python-loops.html",
            kind="textbook",
            license="免费在线访问",
            notes="中文编程教程网站，提供简洁的循环语法示例和练习。",
        ),
    ],
    "Python 条件判断": [
        ExternalKnowledgeResource(
            title="Think Python 2e PDF",
            provider="Green Tea Press",
            url="https://greenteapress.com/thinkpython2/thinkpython2.pdf",
            kind="textbook",
            license="CC BY-NC 3.0",
            notes="涵盖条件语句、布尔表达式与基础控制流。",
        ),
        ExternalKnowledgeResource(
            title="Think Python 2e HTML",
            provider="Green Tea Press",
            url="https://greenteapress.com/thinkpython2/html/index.html",
            kind="textbook",
            license="CC BY-NC 3.0",
            notes="官方网页版本，适合课堂快速跳转展示。",
        ),
        ExternalKnowledgeResource(
            title="Python 官方教程 - 控制流",
            provider="Python.org",
            url="https://docs.python.org/zh-cn/3/tutorial/controlflow.html",
            kind="textbook",
            license="PSF License",
            notes="Python 官方中文教程，详细讲解 if/elif/else 条件判断。",
        ),
        ExternalKnowledgeResource(
            title="菜鸟教程 - Python 条件语句",
            provider="菜鸟教程",
            url="https://www.runoob.com/python/python-if-statement.html",
            kind="textbook",
            license="免费在线访问",
            notes="简洁的条件判断语法示例和实践练习。",
        ),
        ExternalKnowledgeResource(
            title="廖雪峰 - Python 条件判断",
            provider="廖雪峰",
            url="https://www.liaoxuefeng.com/wiki/1016959663602400/1017099478626848",
            kind="textbook",
            license="免费在线访问",
            notes="通俗易懂的中文条件判断教程。",
        ),
    ],
    "数据结构：线性表、栈与队列": [
        ExternalKnowledgeResource(
            title="OpenDSA Modules Collection",
            provider="OpenDSA",
            url="https://opendsa-server.cs.vt.edu/ODSA/Books/Everything/html/",
            kind="interactive",
            license="MIT",
            notes="官方交互式数据结构教材，含线性表、栈、队列、排序与搜索模块。",
        ),
        ExternalKnowledgeResource(
            title="MIT 6.006 Introduction to Algorithms",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="官方讲义页，覆盖数据结构与算法分析核心内容。",
        ),
        ExternalKnowledgeResource(
            title="VisuAlgo - 数据结构可视化",
            provider="National University of Singapore",
            url="https://visualgo.net/zh",
            kind="interactive",
            license="免费访问",
            notes="交互式数据结构和算法可视化工具，支持中文，适合动画演示。",
        ),
        ExternalKnowledgeResource(
            title="数据结构（C语言版）- 浙江大学",
            provider="中国大学MOOC",
            url="https://www.icourse163.org/course/ZJU-93001",
            kind="video",
            license="免费访问",
            notes="陈越、何钦铭教授主讲的数据结构MOOC课程。",
        ),
    ],
    "算法分析：复杂度、递归与分治": [
        ExternalKnowledgeResource(
            title="MIT 6.006 Lecture Notes",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/lecture-notes/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="官方算法课程讲义，覆盖复杂度、递归、分治与常见算法范式。",
        ),
        ExternalKnowledgeResource(
            title="MIT 6.006 Lecture Videos",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/video_galleries/lecture-videos/",
            kind="video",
            license="CC BY-NC-SA 4.0",
            notes="完整课程视频，适合教师选片段投放。",
        ),
        ExternalKnowledgeResource(
            title="OpenDSA Sorting Chapter",
            provider="OpenDSA",
            url="https://opendsa-server.cs.vt.edu/ODSA/Books/Everything/html/InSort.html",
            kind="interactive",
            license="MIT",
            notes="官方交互模块，适合配合复杂度分析讲解排序与分治。",
        ),
        ExternalKnowledgeResource(
            title="算法导论（CLRS）配套网站",
            provider="MIT Press",
            url="https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/",
            kind="textbook",
            license="教材配套资源",
            notes="算法导论官方网站，提供勘误和补充资料。",
        ),
        ExternalKnowledgeResource(
            title="LeetCode 算法题库",
            provider="LeetCode",
            url="https://leetcode.cn/problemset/all/",
            kind="practice",
            license="免费访问",
            notes="中文算法练习平台，按难度和类型分类，适合实践训练。",
        ),
    ],
    "数据库系统：关系模型、SQL 与事务": [
        ExternalKnowledgeResource(
            title="MIT 6.830 Database Systems",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-830-database-systems-fall-2010/",
            kind="course",
            license="CC BY-NC-SA 4.0",
            notes="官方课程主页，覆盖关系模型、查询处理、索引与事务。",
        ),
        ExternalKnowledgeResource(
            title="MIT 6.830 Lecture Notes",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-830-database-systems-fall-2010/pages/lecture-notes/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="官方讲义页，适合直接挂接到知识库。",
        ),
        ExternalKnowledgeResource(
            title="SQL 教程 - 菜鸟教程",
            provider="菜鸟教程",
            url="https://www.runoob.com/sql/sql-tutorial.html",
            kind="textbook",
            license="免费在线访问",
            notes="中文 SQL 基础教程，涵盖查询、连接、事务等核心概念。",
        ),
        ExternalKnowledgeResource(
            title="CMU 15-445 Database Systems",
            provider="Carnegie Mellon University",
            url="https://15445.courses.cs.cmu.edu/",
            kind="course",
            license="免费访问",
            notes="CMU 数据库系统课程，包含视频讲座和作业。",
        ),
    ],
    "操作系统：进程、线程与内存管理": [
        ExternalKnowledgeResource(
            title="Operating Systems: Three Easy Pieces",
            provider="University of Wisconsin-Madison",
            url="https://pages.cs.wisc.edu/~remzi/OSTEP/",
            kind="textbook",
            license="Free online access; see site terms",
            notes="官方免费在线章节，适合外链使用；站点建议教师直接链接原站，不要本地镜像。",
        ),
        ExternalKnowledgeResource(
            title="MIT 6.828 Lecture Notes and Readings",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-828-operating-system-engineering-fall-2012/pages/lecture-notes-and-readings/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="官方讲义与阅读材料，覆盖进程、虚拟内存、文件系统等。",
        ),
        ExternalKnowledgeResource(
            title="清华大学操作系统课程",
            provider="学堂在线",
            url="https://www.xuetangx.com/course/THU08091000267/",
            kind="video",
            license="免费访问",
            notes="向勇、陈渝教授主讲的操作系统 MOOC 课程。",
        ),
        ExternalKnowledgeResource(
            title="操作系统概念（配套网站）",
            provider="Abraham Silberschatz",
            url="https://www.os-book.com/",
            kind="textbook",
            license="教材配套资源",
            notes="Operating System Concepts 官方网站，提供补充材料和习题。",
        ),
    ],
    "计算机网络：分层模型、TCP/IP 与 HTTP": [
        ExternalKnowledgeResource(
            title="Beej's Guide to Network Concepts",
            provider="Beej.us",
            url="https://beej.us/guide/bgnet0/html/",
            kind="textbook",
            license="CC BY-NC-ND 3.0",
            notes="官方网络入门教材，适合分层、IP、路由与传输层入门；建议外链，不做改写镜像。",
        ),
        ExternalKnowledgeResource(
            title="计算机网络：自顶向下方法（配套网站）",
            provider="Pearson Education",
            url="https://gaia.cs.umass.edu/kurose_ross/",
            kind="textbook",
            license="教材配套资源",
            notes="Kurose & Ross 经典教材官方网站，提供 Wireshark 实验和补充材料。",
        ),
        ExternalKnowledgeResource(
            title="HTTP 教程 - MDN Web Docs",
            provider="Mozilla",
            url="https://developer.mozilla.org/zh-CN/docs/Web/HTTP",
            kind="textbook",
            license="CC BY-SA 2.5",
            notes="Mozilla 开发者网络的 HTTP 协议中文文档，权威且详细。",
        ),
        ExternalKnowledgeResource(
            title="计算机网络 - 中国大学MOOC",
            provider="哈尔滨工业大学",
            url="https://www.icourse163.org/course/HIT-154005",
            kind="video",
            license="免费访问",
            notes="李全龙教授主讲的计算机网络MOOC课程。",
        ),
    ],
    "软件工程：需求、架构与测试": [
        ExternalKnowledgeResource(
            title="MIT 6.005 Software Construction",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-005-software-construction-spring-2016/",
            kind="course",
            license="CC BY-NC-SA 4.0",
            notes="官方课程主页，覆盖规格、测试、抽象数据类型与设计模式。",
        ),
        ExternalKnowledgeResource(
            title="MIT 6.005 Readings",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/6-005-software-construction-spring-2016/pages/readings/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="按主题组织的阅读材料，适合教师快速选片段。",
        ),
        ExternalKnowledgeResource(
            title="OpenDSA CS2 Software Design Topics",
            provider="OpenDSA",
            url="https://opendsa-server.cs.vt.edu/ODSA/Books/CS2/html/IntroDSA.html",
            kind="interactive",
            license="MIT",
            notes="含 UML、设计模式、开发过程等软件工程基础主题。",
        ),
        ExternalKnowledgeResource(
            title="软件工程 - 北京大学",
            provider="中国大学MOOC",
            url="https://www.icourse163.org/course/PKU-1002531007",
            kind="video",
            license="免费访问",
            notes="北京大学软件工程MOOC课程，覆盖需求分析、设计与测试。",
        ),
        ExternalKnowledgeResource(
            title="测试驱动开发（TDD）指南",
            provider="Martin Fowler",
            url="https://martinfowler.com/bliki/TestDrivenDevelopment.html",
            kind="textbook",
            license="免费访问",
            notes="Martin Fowler的TDD经典文章，讲解测试驱动开发理念。",
        ),
    ],
    "线性代数：矩阵、向量空间与特征值": [
        ExternalKnowledgeResource(
            title="MIT 18.06 Linear Algebra",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/",
            kind="course",
            license="CC BY-NC-SA 4.0",
            notes="Gilbert Strang 官方课程主页，适合矩阵、向量空间与特征值教学。",
        ),
        ExternalKnowledgeResource(
            title="MIT 18.06 Resources and Exams",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/download/",
            kind="lecture_notes",
            license="CC BY-NC-SA 4.0",
            notes="官方下载页，含考试题与解答，可作为讲义补充。",
        ),
        ExternalKnowledgeResource(
            title="3Blue1Brown - 线性代数的本质",
            provider="3Blue1Brown",
            url="https://www.3blue1brown.com/topics/linear-algebra",
            kind="video",
            license="免费访问",
            notes="著名数学可视化频频道，用动画直观讲解线性代数核心概念。",
        ),
        ExternalKnowledgeResource(
            title="线性代数 - 同济大学版配套视频",
            provider="B站",
            url="https://www.bilibili.com/video/BV1ib411t7YR",
            kind="video",
            license="免费访问",
            notes="国内流行的线性代数教学视频，配合同济版教材。",
        ),
    ],
    "概率统计：随机变量、期望与贝叶斯思想": [
        ExternalKnowledgeResource(
            title="MIT 18.05 Introduction to Probability and Statistics",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2022/",
            kind="course",
            license="CC BY-NC-SA 4.0",
            notes="官方课程主页，覆盖随机变量、分布、贝叶斯推断与统计方法。",
        ),
        ExternalKnowledgeResource(
            title="MIT 18.05 Download Package",
            provider="MIT OpenCourseWare",
            url="https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2022/download/",
            kind="textbook",
            license="CC BY-NC-SA 4.0",
            notes="官方课程打包下载页，适合教师离线备课。",
        ),
        ExternalKnowledgeResource(
            title="概率论与数理统计 - 浙江大学",
            provider="中国大学MOOC",
            url="https://www.icourse163.org/course/ZJU-232005",
            kind="video",
            license="免费访问",
            notes="浙江大学概率统计MOOC课程。",
        ),
        ExternalKnowledgeResource(
            title="Seeing Theory - 概率统计可视化",
            provider="Brown University",
            url="https://seeing-theory.brown.edu/",
            kind="interactive",
            license="免费访问",
            notes="交互式概率统计可视化教材，直观展示概率分布和统计概念。",
        ),
    ],
}


def resources_for_article(title: str) -> list[ExternalKnowledgeResource]:
    """Return external resources linked to one curated article title."""

    return RESOURCE_CATALOG.get(title, [])
