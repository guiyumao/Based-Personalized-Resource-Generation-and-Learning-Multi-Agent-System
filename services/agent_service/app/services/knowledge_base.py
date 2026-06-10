"""Curated knowledge snippets used to ground courseware and exercise generation."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class KnowledgeArticle:
    """One curated knowledge article for a learning topic."""

    title: str
    subject: str
    level: str
    summary: str
    concepts: list[str]
    syntax: list[str]
    examples: list[str]
    mistakes: list[str]
    applications: list[str]
    checks: list[str]


class KnowledgeBaseService:
    """Provide curated topic knowledge before falling back to generic generation."""

    def __init__(self) -> None:
        self._articles: list[tuple[tuple[str, ...], KnowledgeArticle]] = [
            (
                ("python 循环", "循环", "for 循环", "while 循环", "python loop"),
                KnowledgeArticle(
                    title="Python 循环",
                    subject="程序设计基础",
                    level="大学基础",
                    summary=(
                        "循环的核心作用，是让程序按照规则重复执行一类操作。"
                        "当我们需要遍历一组数据、持续判断条件、批量处理任务时，循环就是最常用的基础工具。"
                    ),
                    concepts=[
                        "`for` 更适合遍历已知序列，比如列表、字符串、字典键或 `range()` 产生的范围。",
                        "`while` 更适合在条件成立时持续执行，常见于循环次数不固定、需要根据状态决定是否继续的场景。",
                        "写循环时不能只盯着语法，还要同时想清楚三件事：重复的对象是谁、继续的条件是什么、什么时候结束。",
                        "循环体里的缩进非常关键，缩进层级错了，程序的执行逻辑就会完全变化。",
                    ],
                    syntax=[
                        "for item in items:\n    print(item)",
                        "for index in range(5):\n    print(index)",
                        "count = 0\nwhile count < 3:\n    print(count)\n    count += 1",
                    ],
                    examples=[
                        (
                            "scores = [78, 91, 59, 84, 67]\n"
                            "for score in scores:\n"
                            "    if score >= 60:\n"
                            "        print(score, '及格')\n"
                            "    else:\n"
                            "        print(score, '不及格')"
                        ),
                        (
                            "count = 1\n"
                            "while count <= 5:\n"
                            "    print(f'第 {count} 次练习')\n"
                            "    count += 1"
                        ),
                    ],
                    mistakes=[
                        "在 `while` 循环里忘记更新控制变量，导致死循环。",
                        "把 `range(5)` 误认为是 1 到 5，实际上它表示 0 到 4。",
                        "循环体缩进错误，导致判断或更新语句并没有真正放进循环里。",
                        "本来是遍历固定序列，却强行使用 `while`，让代码变得更绕、更难检查。",
                    ],
                    applications=[
                        "批量处理一组数据，比如遍历成绩、订单、日志记录。",
                        "反复执行某个动作直到满足条件，比如输入校验、状态轮询。",
                        "在列表中完成筛选、统计、累加、查找等任务。",
                        "在编程题中实现计数、求和、打印图形等基础逻辑。",
                    ],
                    checks=[
                        "我能不能说清 `for` 和 `while` 各自适合什么场景？",
                        "我能不能解释一个 `while` 循环为什么会变成死循环？",
                        "我能不能写出一个遍历列表并带条件判断的小程序？",
                        "我能不能在代码里指出循环对象、循环条件和更新步骤？",
                    ],
                ),
            ),
            (
                ("python 条件判断", "条件判断", "if else", "条件语句", "python if"),
                KnowledgeArticle(
                    title="Python 条件判断",
                    subject="程序设计基础",
                    level="大学基础",
                    summary=(
                        "条件判断让程序能够根据不同情况选择不同分支。"
                        "它经常和循环配合使用，用来筛选数据、控制流程、处理边界情况。"
                    ),
                    concepts=[
                        "`if` 表示当条件成立时执行。",
                        "`elif` 用来处理多个互斥条件，避免写出互相冲突的多个 `if`。",
                        "`else` 负责兜底，当前面条件都不成立时执行。",
                        "条件语句最容易出错的地方，通常是区间边界、比较运算符和条件顺序。",
                    ],
                    syntax=[
                        "if score >= 60:\n    print('及格')\nelse:\n    print('不及格')",
                        "if x > 0:\n    print('正数')\nelif x == 0:\n    print('零')\nelse:\n    print('负数')",
                    ],
                    examples=[
                        (
                            "score = 85\n"
                            "if score >= 90:\n"
                            "    print('A')\n"
                            "elif score >= 80:\n"
                            "    print('B')\n"
                            "else:\n"
                            "    print('C')"
                        )
                    ],
                    mistakes=[
                        "把 `=` 和 `==` 混用。",
                        "条件顺序写反，导致宽范围条件先命中。",
                        "该用 `elif` 的地方写成多个并列 `if`，造成逻辑冲突。",
                    ],
                    applications=[
                        "成绩评级、权限校验、输入合法性判断。",
                        "配合循环筛选满足条件的数据。",
                    ],
                    checks=[
                        "我能不能解释 `if / elif / else` 的执行顺序？",
                        "我能不能根据题意写出正确的条件区间？",
                    ],
                ),
            ),
            (
                ("数据结构", "线性表", "顺序表", "链表", "栈", "队列", "data structure"),
                KnowledgeArticle(
                    title="数据结构：线性表、栈与队列",
                    subject="数据结构",
                    level="大学核心",
                    summary=(
                        "数据结构研究数据元素之间的组织方式及其操作代价。"
                        "线性表、栈、队列是后续树、图、索引结构和算法分析的基础。"
                    ),
                    concepts=[
                        "线性表强调元素之间的一对一前后继关系，顺序表适合随机访问，链表适合频繁插入删除。",
                        "栈是后进先出结构，常用于函数调用、表达式求值、括号匹配和回溯。",
                        "队列是先进先出结构，常用于任务调度、广度优先搜索和缓冲区管理。",
                        "评价数据结构时要同时考虑时间复杂度、空间复杂度、访问模式和更新频率。",
                    ],
                    syntax=[
                        "顺序表随机访问：A[i] 的时间复杂度通常为 O(1)",
                        "单链表插入：找到前驱结点后修改 next 指针",
                        "栈操作：push / pop / top；队列操作：enqueue / dequeue / front",
                    ],
                    examples=[
                        "用栈检查表达式括号是否匹配：遇到左括号入栈，遇到右括号弹栈匹配。",
                        "用队列实现 BFS：起点入队，循环取队首并扩展未访问邻居。",
                    ],
                    mistakes=[
                        "只记住定义，忽略不同结构在随机访问、插入删除上的代价差异。",
                        "链表插入删除时没有保存前驱或后继指针，导致链断裂。",
                        "把栈和队列的出入顺序混淆，导致算法过程错误。",
                    ],
                    applications=[
                        "操作系统进程调度、编译器语法分析、数据库缓冲区管理。",
                        "图搜索、表达式计算、递归转迭代、撤销/重做机制。",
                    ],
                    checks=[
                        "我能不能比较顺序表和链表在查询、插入、删除上的复杂度？",
                        "我能不能用栈解释递归调用过程？",
                        "我能不能手推一次队列驱动的 BFS 过程？",
                    ],
                ),
            ),
            (
                ("算法分析", "时间复杂度", "空间复杂度", "递归", "分治", "algorithm complexity"),
                KnowledgeArticle(
                    title="算法分析：复杂度、递归与分治",
                    subject="算法设计与分析",
                    level="大学核心",
                    summary=(
                        "算法分析关注问题规模增长时资源消耗如何变化。"
                        "复杂度、递归式和分治思想是理解排序、搜索、动态规划等算法的基础。"
                    ),
                    concepts=[
                        "时间复杂度描述运行时间随输入规模增长的数量级，常用 O、Ω、Θ 表示上界、下界和紧确界。",
                        "空间复杂度关注额外内存使用，递归算法还需要考虑调用栈深度。",
                        "分治法将问题拆成子问题，分别求解后合并结果，关键在于子问题独立性和合并代价。",
                        "递归式如 T(n)=2T(n/2)+O(n) 可用于分析归并排序等分治算法。",
                    ],
                    syntax=[
                        "常见阶：O(1) < O(log n) < O(n) < O(n log n) < O(n²) < O(2ⁿ)",
                        "Master 定理常见形态：T(n)=aT(n/b)+f(n)",
                    ],
                    examples=[
                        "归并排序将数组二分，分别排序后线性合并，时间复杂度为 O(n log n)。",
                        "二分查找每次排除一半搜索空间，时间复杂度为 O(log n)。",
                    ],
                    mistakes=[
                        "把循环次数和复杂度机械等同，忽略循环变量倍增或递减模式。",
                        "只分析最外层循环，遗漏嵌套循环或递归调用的累计代价。",
                        "忽略输入规模定义，例如图算法中同时存在顶点数 V 和边数 E。",
                    ],
                    applications=[
                        "选择合适算法、评估系统瓶颈、面试算法题推理、工程性能优化。",
                        "排序、搜索、图算法、数据库查询优化和机器学习训练复杂度估算。",
                    ],
                    checks=[
                        "我能不能说明 O、Ω、Θ 的区别？",
                        "我能不能为一段嵌套循环推导复杂度？",
                        "我能不能写出归并排序的递归式并解释每一项含义？",
                    ],
                ),
            ),
            (
                ("数据库", "关系模型", "sql", "事务", "索引", "范式", "database"),
                KnowledgeArticle(
                    title="数据库系统：关系模型、SQL 与事务",
                    subject="数据库系统",
                    level="大学核心",
                    summary=(
                        "数据库系统关注数据的结构化组织、可靠存储和高效查询。"
                        "关系模型、SQL、索引、事务和范式是理解应用数据层的核心。"
                    ),
                    concepts=[
                        "关系模型用表、行、列表达实体和属性，主键用于唯一标识记录，外键表达表间关联。",
                        "SQL 包含数据查询、定义、操作和控制语言，查询语句的核心是选择、投影、连接和聚合。",
                        "索引通过额外数据结构提升查询效率，但会增加写入维护成本。",
                        "事务 ACID 分别表示原子性、一致性、隔离性和持久性。",
                    ],
                    syntax=[
                        "SELECT column FROM table WHERE condition GROUP BY column HAVING condition",
                        "JOIN 用于按照关联条件组合多张表的数据",
                        "事务边界：BEGIN / COMMIT / ROLLBACK",
                    ],
                    examples=[
                        "学生表 students 与成绩表 scores 可通过 student_id 外键关联查询。",
                        "为高频过滤字段建立索引，可以减少全表扫描，但频繁更新字段不一定适合建索引。",
                    ],
                    mistakes=[
                        "把 WHERE 和 HAVING 混用，前者过滤行，后者过滤聚合后的分组。",
                        "滥用索引，忽略写入成本和选择性。",
                        "忽略事务隔离级别，导致脏读、不可重复读或幻读问题。",
                    ],
                    applications=[
                        "教务系统、学习记录、用户画像、资源管理、报表统计和审计日志。",
                        "后端服务的数据建模、查询性能优化和并发一致性控制。",
                    ],
                    checks=[
                        "我能不能画出一个实体关系模型并标注主外键？",
                        "我能不能写出包含 JOIN、GROUP BY 的统计查询？",
                        "我能不能解释事务 ACID 在真实系统中的意义？",
                    ],
                ),
            ),
            (
                ("操作系统", "进程", "线程", "内存管理", "文件系统", "os"),
                KnowledgeArticle(
                    title="操作系统：进程、线程与内存管理",
                    subject="操作系统",
                    level="大学核心",
                    summary=(
                        "操作系统负责管理 CPU、内存、文件和 I/O 设备，为应用程序提供抽象和资源调度。"
                        "进程线程、同步互斥、虚拟内存和文件系统是课程主线。"
                    ),
                    concepts=[
                        "进程是资源分配的基本单位，线程是 CPU 调度的基本单位。",
                        "并发程序需要处理临界区、互斥、同步和死锁问题。",
                        "虚拟内存通过地址映射让程序拥有连续地址空间，分页机制支持按需调入和隔离保护。",
                        "文件系统负责持久化数据的命名、组织、访问控制和空间管理。",
                    ],
                    syntax=[
                        "进程状态：新建、就绪、运行、阻塞、终止",
                        "死锁必要条件：互斥、占有并等待、不可抢占、循环等待",
                    ],
                    examples=[
                        "生产者-消费者问题展示了缓冲区、互斥锁和条件同步的组合使用。",
                        "页面置换算法如 FIFO、LRU 用于决定物理内存不足时换出哪个页面。",
                    ],
                    mistakes=[
                        "把并发和并行混为一谈：并发强调逻辑上同时推进，并行强调物理上同时执行。",
                        "只加锁不考虑锁顺序，可能引入死锁。",
                        "忽略上下文切换和同步开销，误以为线程越多越快。",
                    ],
                    applications=[
                        "后端服务并发处理、数据库锁、容器资源隔离、性能调优和系统故障排查。",
                        "理解应用程序如何使用 CPU、内存、磁盘和网络资源。",
                    ],
                    checks=[
                        "我能不能区分进程和线程？",
                        "我能不能用死锁四个必要条件分析一个阻塞场景？",
                        "我能不能解释虚拟内存为什么需要页表？",
                    ],
                ),
            ),
            (
                ("计算机网络", "网络", "tcp", "http", "ip", "osi", "network"),
                KnowledgeArticle(
                    title="计算机网络：分层模型、TCP/IP 与 HTTP",
                    subject="计算机网络",
                    level="大学核心",
                    summary=(
                        "计算机网络通过分层协议把主机、路由器和应用连接起来。"
                        "理解 TCP/IP、路由、可靠传输和 HTTP，有助于分析 Web 系统的数据流。"
                    ),
                    concepts=[
                        "分层模型将复杂通信拆成应用层、传输层、网络层、链路层等职责。",
                        "IP 负责跨网络寻址和路由，TCP 在不可靠网络上提供可靠、有序、面向连接的字节流。",
                        "UDP 不保证可靠性，但延迟低、开销小，适合实时音视频、DNS 等场景。",
                        "HTTP 是应用层协议，常用于浏览器与服务端之间的请求响应通信。",
                    ],
                    syntax=[
                        "HTTP 请求：method path headers body",
                        "TCP 可靠性机制：序号、确认、重传、滑动窗口、拥塞控制",
                    ],
                    examples=[
                        "浏览器访问页面时通常经历 DNS 解析、TCP/TLS 建连、HTTP 请求和响应渲染。",
                        "接口超时可能发生在 DNS、连接建立、服务处理、网络传输等多个环节。",
                    ],
                    mistakes=[
                        "把 IP 地址、端口、域名三个概念混淆。",
                        "只看到 HTTP 状态码，忽略传输层连接和服务端日志。",
                        "误以为 TCP 一定比 UDP 更好，忽略业务对延迟和可靠性的取舍。",
                    ],
                    applications=[
                        "前后端接口调试、微服务通信、Web 性能优化、网络故障定位和安全分析。",
                        "理解 API 请求、网关、负载均衡和跨域配置。",
                    ],
                    checks=[
                        "我能不能说明一次 HTTP 请求背后的网络步骤？",
                        "我能不能区分 TCP 和 UDP 的适用场景？",
                        "我能不能解释端口在进程通信中的作用？",
                    ],
                ),
            ),
            (
                ("软件工程", "需求分析", "架构", "测试", "uml", "software engineering"),
                KnowledgeArticle(
                    title="软件工程：需求、架构与测试",
                    subject="软件工程",
                    level="大学核心",
                    summary=(
                        "软件工程关注如何系统化地构建可维护、可验证、可演进的软件。"
                        "需求分析、架构设计、版本管理、测试和迭代交付构成工程实践主线。"
                    ),
                    concepts=[
                        "需求分析需要区分业务目标、用户需求、功能需求和非功能需求。",
                        "架构设计关注模块边界、数据流、依赖关系、性能、安全和可扩展性。",
                        "测试覆盖单元测试、集成测试、系统测试和验收测试，不同层级验证不同风险。",
                        "持续集成通过自动构建、测试和检查降低集成风险。",
                    ],
                    syntax=[
                        "常见图：用例图、类图、时序图、数据流图、部署图",
                        "测试金字塔：单元测试多，端到端测试少而关键",
                    ],
                    examples=[
                        "一个学习平台可拆分为用户服务、资源生成服务、测评服务、教师服务和前端应用。",
                        "接口变更前需要同步更新类型定义、文档、前端调用和测试用例。",
                    ],
                    mistakes=[
                        "直接写代码但没有确认需求边界，导致反复返工。",
                        "把所有逻辑堆在一个模块里，后续难以测试和维护。",
                        "只做 happy path 测试，忽略异常分支和权限边界。",
                    ],
                    applications=[
                        "课程设计、毕业设计、团队项目、需求文档、接口文档和系统架构图。",
                        "把复杂系统拆成可迭代交付的模块。",
                    ],
                    checks=[
                        "我能不能把一个需求拆成输入、处理、输出和异常分支？",
                        "我能不能说明当前系统的核心模块和数据流？",
                        "我能不能为一个接口设计正常和异常测试用例？",
                    ],
                ),
            ),
            (
                ("线性代数", "矩阵", "向量空间", "特征值", "linear algebra"),
                KnowledgeArticle(
                    title="线性代数：矩阵、向量空间与特征值",
                    subject="高等数学与线性代数",
                    level="大学基础",
                    summary=(
                        "线性代数用向量、矩阵和线性变换描述多维空间中的结构。"
                        "它是机器学习、图形学、优化和数据分析的重要数学基础。"
                    ),
                    concepts=[
                        "矩阵可以表示线性方程组、线性变换和数据表征。",
                        "向量空间关注加法和数乘封闭性，基和维数描述空间的独立方向数量。",
                        "秩反映矩阵行列向量的最大线性无关数量，也影响方程组解的结构。",
                        "特征值和特征向量描述线性变换中方向不变、只发生伸缩的向量。",
                    ],
                    syntax=[
                        "线性方程组：Ax=b",
                        "特征方程：det(A-λI)=0",
                    ],
                    examples=[
                        "二维旋转、缩放和投影都可以用矩阵乘法表示。",
                        "PCA 利用特征值分解寻找数据方差最大的方向。",
                    ],
                    mistakes=[
                        "只会机械行变换，不理解秩、基、维数和解空间之间的关系。",
                        "把矩阵乘法当成逐元素相乘。",
                        "忽略矩阵是否可逆、是否方阵等前提条件。",
                    ],
                    applications=[
                        "机器学习特征表示、推荐系统、图像处理、计算机图形学和科学计算。",
                        "解线性方程组、降维、坐标变换和稳定性分析。",
                    ],
                    checks=[
                        "我能不能解释矩阵乘法为什么代表线性变换复合？",
                        "我能不能通过秩判断线性方程组解的情况？",
                        "我能不能说明特征值在数据降维中的意义？",
                    ],
                ),
            ),
            (
                ("概率论", "统计", "随机变量", "期望", "方差", "贝叶斯", "probability"),
                KnowledgeArticle(
                    title="概率统计：随机变量、期望与贝叶斯思想",
                    subject="概率论与数理统计",
                    level="大学基础",
                    summary=(
                        "概率统计研究不确定性数据的建模、推断和决策。"
                        "随机变量、分布、期望、方差、条件概率和贝叶斯公式是数据分析基础。"
                    ),
                    concepts=[
                        "随机变量把随机试验结果映射为数值，分布描述各结果出现的概率规律。",
                        "期望表示长期平均水平，方差描述数据围绕均值的离散程度。",
                        "条件概率刻画在已知事件发生时另一个事件发生的可能性。",
                        "贝叶斯公式用于用新证据更新先验认知，是很多智能系统推断的基础。",
                    ],
                    syntax=[
                        "条件概率：P(A|B)=P(A∩B)/P(B)",
                        "贝叶斯公式：P(A|B)=P(B|A)P(A)/P(B)",
                        "期望：E(X)=ΣxP(X=x)",
                    ],
                    examples=[
                        "垃圾邮件过滤可根据词语出现情况更新邮件属于垃圾邮件的概率。",
                        "考试成绩分布可以用均值、方差和分位数描述整体学习情况。",
                    ],
                    mistakes=[
                        "混淆 P(A|B) 和 P(B|A)。",
                        "只看平均值，忽略方差和异常值。",
                        "把相关性误认为因果关系。",
                    ],
                    applications=[
                        "机器学习、数据分析、推荐系统、A/B 测试、质量控制和风险评估。",
                        "从学习行为数据中估计掌握度和错误风险。",
                    ],
                    checks=[
                        "我能不能解释条件概率和联合概率的区别？",
                        "我能不能用贝叶斯公式完成一次后验概率计算？",
                        "我能不能说明均值相同但方差不同意味着什么？",
                    ],
                ),
            ),
        ]

    def get_article(self, knowledge_point: str) -> KnowledgeArticle | None:
        """Return a curated article for a knowledge point if one exists."""

        normalized = knowledge_point.strip().lower()
        for aliases, article in self._articles:
            if any(alias in normalized or normalized in alias for alias in aliases):
                return article
        return None

    def list_articles(self, subject: str | None = None) -> list[KnowledgeArticle]:
        """Return curated articles, optionally filtered by subject."""

        normalized_subject = subject.strip().lower() if subject else ""
        articles = [article for _, article in self._articles]
        if not normalized_subject:
            return articles
        return [
            article
            for article in articles
            if normalized_subject in article.subject.lower() or normalized_subject in article.title.lower()
        ]

    def list_subjects(self) -> list[str]:
        """Return available university knowledge subjects."""

        return sorted({article.subject for _, article in self._articles})

    def article_to_dict(self, article: KnowledgeArticle) -> dict[str, object]:
        """Serialize one article for API responses."""

        return {
            "id": self._slugify(article.title),
            "title": article.title,
            "subject": article.subject,
            "level": article.level,
            "summary": article.summary,
            "concepts": article.concepts,
            "syntax": article.syntax,
            "examples": article.examples,
            "mistakes": article.mistakes,
            "applications": article.applications,
            "checks": article.checks,
        }

    def search_by_keywords(self, question: str, top_k: int = 3) -> list[KnowledgeArticle]:
        """Return the most relevant curated articles for a learner question."""

        keywords = self._extract_keywords(question)
        if not keywords:
            return []

        scored: list[tuple[int, KnowledgeArticle]] = []
        for aliases, article in self._articles:
            haystacks = [article.title.lower(), article.summary.lower(), *[alias.lower() for alias in aliases]]
            haystacks.extend(item.lower() for item in article.concepts[:4])
            haystacks.extend(item.lower() for item in article.mistakes[:4])

            score = 0
            for keyword in keywords:
                if any(text == keyword for text in haystacks):
                    score += 10
                elif any(keyword in text for text in haystacks):
                    score += 4
            if score > 0:
                scored.append((score, article))

        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[KnowledgeArticle] = []
        seen_titles: set[str] = set()
        for _, article in scored:
            if article.title in seen_titles:
                continue
            results.append(article)
            seen_titles.add(article.title)
            if len(results) >= top_k:
                break
        return results

    def _slugify(self, text: str) -> str:
        return re.sub(r"[\s：、，,]+", "-", text.strip().lower()).strip("-")

    def _extract_keywords(self, question: str) -> list[str]:
        tokens = [
            token.strip().lower()
            for token in re.split(r"[\s，。！？,!.?；;：:、（）()]+", question)
            if token.strip()
        ]
        return [token for token in tokens if len(token) >= 2]
