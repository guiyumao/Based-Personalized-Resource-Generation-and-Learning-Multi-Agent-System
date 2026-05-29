"""Curated knowledge snippets used to ground courseware and exercise generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeArticle:
    """One curated knowledge article for a learning topic."""

    title: str
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
        self._articles = {
            "python 循环": KnowledgeArticle(
                title="Python 循环",
                summary=(
                    "循环用于处理重复任务。当一段逻辑需要执行多次时，"
                    "可以使用 `for` 或 `while` 让程序自动重复执行。"
                ),
                concepts=[
                    "`for` 适合遍历序列、列表、字符串、字典和 range。",
                    "`while` 适合在条件成立时持续执行，常用于未知循环次数的场景。",
                    "循环通常会和条件判断、计数器、累加器一起出现。",
                    "循环体内部的缩进决定了哪些语句会被重复执行。",
                ],
                syntax=[
                    "for item in items:\n    print(item)",
                    "for index in range(5):\n    print(index)",
                    "count = 0\nwhile count < 3:\n    print(count)\n    count += 1",
                ],
                examples=[
                    (
                        "遍历成绩列表并判断是否及格：\n"
                        "scores = [78, 91, 59, 84, 67]\n"
                        "for score in scores:\n"
                        "    if score >= 60:\n"
                        "        print(score, '及格')\n"
                        "    else:\n"
                        "        print(score, '不及格')"
                    ),
                    (
                        "使用 while 实现简单计数器：\n"
                        "count = 1\n"
                        "while count <= 5:\n"
                        "    print('第', count, '次练习')\n"
                        "    count += 1"
                    ),
                ],
                mistakes=[
                    "忘记更新 while 循环的条件变量，导致死循环。",
                    "把 range(5) 误解成从 1 到 5，实际是 0 到 4。",
                    "循环体缩进错误，导致本该重复执行的语句跑到循环外。",
                    "在不需要 while 的地方强行使用 while，代码可读性变差。",
                ],
                applications=[
                    "批量处理一组数据，例如遍历成绩、订单、日志记录。",
                    "重复请求或轮询某个状态，直到满足退出条件。",
                    "对列表中的每个元素做过滤、格式化或统计。",
                    "在编程题中实现计数、累加、搜索和表格输出。",
                ],
                checks=[
                    "能否解释 for 和 while 的使用场景差异？",
                    "能否写出一个遍历列表并带条件判断的循环？",
                    "能否判断一个 while 循环为什么会死循环？",
                    "能否用循环解决一个重复输出或统计的问题？",
                ],
            ),
            "python 条件判断": KnowledgeArticle(
                title="Python 条件判断",
                summary=(
                    "条件判断用于让程序根据不同情况选择不同分支。"
                    "常见形式是 `if / elif / else`。"
                ),
                concepts=[
                    "`if` 表示当条件成立时执行。",
                    "`elif` 用于处理多个互斥分支。",
                    "`else` 用于兜底情况。",
                    "比较运算符和逻辑运算符决定条件表达式的真假。",
                ],
                syntax=[
                    "if score >= 60:\n    print('及格')\nelse:\n    print('不及格')",
                    "if x > 0:\n    print('正数')\nelif x == 0:\n    print('零')\nelse:\n    print('负数')",
                ],
                examples=[
                    (
                        "根据成绩输出等级：\n"
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
                    "条件顺序写反，导致更宽泛的条件提前命中。",
                    "把 `=` 和 `==` 混淆。",
                    "多个 if 写成并列结构，造成逻辑冲突。",
                ],
                applications=[
                    "成绩评级、权限校验、输入合法性判断。",
                    "配合循环筛选满足条件的数据。",
                ],
                checks=[
                    "能否解释 if、elif、else 的执行顺序？",
                    "能否根据题意写出正确的条件区间？",
                ],
            ),
        }

    def get_article(self, knowledge_point: str) -> KnowledgeArticle | None:
        """Return a curated article for a knowledge point if one exists."""

        normalized = knowledge_point.strip().lower()
        for key, article in self._articles.items():
            if key in normalized or normalized in key:
                return article
        return None
