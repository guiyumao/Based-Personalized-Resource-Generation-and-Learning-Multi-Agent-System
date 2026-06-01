"""Curated knowledge snippets used to ground courseware and exercise generation."""

from __future__ import annotations

from dataclasses import dataclass
import re


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
        self._articles: list[tuple[tuple[str, ...], KnowledgeArticle]] = [
            (
                ("python 循环", "循环", "for 循环", "while 循环", "python loop"),
                KnowledgeArticle(
                    title="Python 循环",
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
        ]

    def get_article(self, knowledge_point: str) -> KnowledgeArticle | None:
        """Return a curated article for a knowledge point if one exists."""

        normalized = knowledge_point.strip().lower()
        for aliases, article in self._articles:
            if any(alias in normalized or normalized in alias for alias in aliases):
                return article
        return None

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

    def _extract_keywords(self, question: str) -> list[str]:
        tokens = [
            token.strip().lower()
            for token in re.split(r"[\s，。！？,!.?；;：:、（）()]+", question)
            if token.strip()
        ]
        return [token for token in tokens if len(token) >= 2]
