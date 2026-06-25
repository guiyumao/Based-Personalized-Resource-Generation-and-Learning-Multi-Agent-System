#!/usr/bin/env python3
"""Crawl educational resources from runoob.com and wikibooks.

Usage:
    python scripts/crawl_resources.py               # crawl all configured URLs
    python scripts/crawl_resources.py --dry-run     # list URLs without fetching
    python scripts/crawl_resources.py --subject python  # crawl one subject only
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
CRAWLED_DIR = ROOT_DIR / "crawled_content"
CRAWLED_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.5  # seconds — be polite


# ── URL Configuration ──────────────────────────────────────────────
@dataclass
class CrawlTarget:
    url: str
    subject: str
    topic: str
    difficulty: str = "基础"
    tags: list[str] = field(default_factory=list)


# fmt: off
TARGETS: list[CrawlTarget] = [
    # ═══════════════ Python 基础 ═══════════════
    CrawlTarget("https://www.runoob.com/python3/python3-tutorial.html",      "python", "Python入门概述",   "基础", ["Python","入门","基础","概念讲解"]),
    CrawlTarget("https://www.runoob.com/python3/python3-data-type.html",     "python", "数据类型",         "基础", ["Python","数据类型","变量","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-number.html",        "python", "数字类型",         "基础", ["Python","数字","int","float","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-string.html",        "python", "字符串操作",       "基础", ["Python","字符串","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-list.html",          "python", "列表操作",         "基础", ["Python","列表","list","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-if-else.html",       "python", "条件判断",         "基础", ["Python","条件判断","if-else","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-loop.html",          "python", "循环结构",         "基础", ["Python","循环","while","for","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-while-loop.html",    "python", "while循环详解",    "基础", ["Python","while","循环","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-for-loop.html",      "python", "for循环详解",      "基础", ["Python","for","循环","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-function.html",      "python", "函数定义与调用",   "基础", ["Python","函数","def","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-class.html",         "python", "面向对象编程",     "进阶", ["Python","OOP","类","对象","进阶"]),
    CrawlTarget("https://www.runoob.com/python3/python3-module.html",        "python", "模块与包",         "进阶", ["Python","模块","import","进阶"]),
    CrawlTarget("https://www.runoob.com/python3/python3-exceptions.html",    "python", "异常处理",         "进阶", ["Python","异常","try-except","进阶"]),
    CrawlTarget("https://www.runoob.com/python3/python3-file-methods.html",  "python", "文件操作",         "基础", ["Python","文件IO","open","基础"]),
    CrawlTarget("https://www.runoob.com/python3/python3-inputoutput.html",   "python", "输入输出",         "基础", ["Python","IO","输入输出","print","input","基础"]),

    # ═══════════════ C 语言基础 ═══════════════
    CrawlTarget("https://www.runoob.com/cprogramming/c-tutorial.html",       "c_lang",  "C语言概述",       "基础", ["C语言","入门","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-data-types.html",     "c_lang",  "数据类型",         "基础", ["C语言","数据类型","int","char","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-decision.html",       "c_lang",  "条件判断",         "基础", ["C语言","条件判断","if-else","switch","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-loops.html",          "c_lang",  "循环结构",         "基础", ["C语言","循环","while","for","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-function.html",       "c_lang",  "函数",             "基础", ["C语言","函数","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-arrays.html",         "c_lang",  "数组",             "基础", ["C语言","数组","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-pointers.html",       "c_lang",  "指针",             "进阶", ["C语言","指针","内存","进阶"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-strings.html",        "c_lang",  "字符串",           "基础", ["C语言","字符串","char[]","基础"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-structures.html",     "c_lang",  "结构体",           "进阶", ["C语言","struct","结构体","进阶"]),
    CrawlTarget("https://www.runoob.com/cprogramming/c-file-io.html",        "c_lang",  "文件操作",         "基础", ["C语言","文件IO","fopen","基础"]),

    # ═══════════════ Java 语言基础 ═══════════════
    CrawlTarget("https://www.runoob.com/java/java-tutorial.html",            "java",    "Java概述",         "基础", ["Java","入门","JVM","基础"]),
    CrawlTarget("https://www.runoob.com/java/java-basic-datatypes.html",     "java",    "数据类型",         "基础", ["Java","数据类型","int","基础"]),
    CrawlTarget("https://www.runoob.com/java/java-if-else-switch.html",      "java",    "条件判断",         "基础", ["Java","条件判断","if-else","基础"]),
    CrawlTarget("https://www.runoob.com/java/java-loop.html",                "java",    "循环结构",         "基础", ["Java","循环","while","for","基础"]),
    CrawlTarget("https://www.runoob.com/java/java-methods.html",             "java",    "方法定义",         "基础", ["Java","方法","函数","基础"]),
    CrawlTarget("https://www.runoob.com/java/java-inheritance.html",         "java",    "继承与多态",       "进阶", ["Java","OOP","继承","多态","进阶"]),
    CrawlTarget("https://www.runoob.com/java/java-encapsulation.html",       "java",    "封装",             "进阶", ["Java","OOP","封装","进阶"]),
    CrawlTarget("https://www.runoob.com/java/java-abstraction.html",         "java",    "抽象类与接口",     "进阶", ["Java","OOP","抽象类","接口","进阶"]),
    CrawlTarget("https://www.runoob.com/java/java-exceptions.html",          "java",    "异常处理",         "进阶", ["Java","异常","try-catch","进阶"]),
    CrawlTarget("https://www.runoob.com/java/java-files-io.html",            "java",    "文件IO",           "基础", ["Java","文件IO","基础"]),

    # ═══════════════ C++ 语言基础 ═══════════════
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-tutorial.html",        "cpp",     "C++概述",          "基础", ["C++","入门","基础"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-data-types.html",      "cpp",     "数据类型",         "基础", ["C++","数据类型","基础"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-loops.html",           "cpp",     "循环结构",         "基础", ["C++","循环","while","for","基础"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-decision.html",        "cpp",     "条件判断",         "基础", ["C++","条件判断","if-else","基础"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-functions.html",       "cpp",     "函数",             "基础", ["C++","函数","基础"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-classes-objects.html", "cpp",     "类与对象",         "进阶", ["C++","OOP","类","对象","进阶"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-inheritance.html",     "cpp",     "继承",             "进阶", ["C++","OOP","继承","进阶"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-pointers.html",        "cpp",     "指针与引用",       "进阶", ["C++","指针","引用","进阶"]),
    CrawlTarget("https://www.runoob.com/cplusplus/cpp-files-streams.html",   "cpp",     "文件流",           "基础", ["C++","文件IO","fstream","基础"]),

    # ═══════════════ 数据结构 ═══════════════
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-tutorial.html", "algorithms","数据结构概述","基础",["数据结构","入门","基础"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-array.html",    "algorithms","数组",        "基础",["数据结构","数组","基础"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-linked-list.html","algorithms","链表",      "基础",["数据结构","链表","基础"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-stack.html",    "algorithms","栈",          "基础",["数据结构","栈","LIFO","基础"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-queue.html",    "algorithms","队列",        "基础",["数据结构","队列","FIFO","基础"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-tree.html",     "algorithms","树",          "进阶",["数据结构","树","二叉树","进阶"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-graph.html",    "algorithms","图",          "进阶",["数据结构","图","进阶"]),
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-hash.html",     "algorithms","哈希表",      "进阶",["数据结构","哈希表","散列","进阶"]),

    # ═══════════════ 算法设计与分析 ═══════════════
    CrawlTarget("https://www.runoob.com/w3cnote/bubble-sort.html",            "algorithms","冒泡排序",     "基础",["算法","排序","冒泡排序","基础"]),
    CrawlTarget("https://www.runoob.com/w3cnote/selection-sort.html",         "algorithms","选择排序",     "基础",["算法","排序","选择排序","基础"]),
    CrawlTarget("https://www.runoob.com/w3cnote/insertion-sort.html",         "algorithms","插入排序",     "基础",["算法","排序","插入排序","基础"]),
    CrawlTarget("https://www.runoob.com/w3cnote/quick-sort.html",             "algorithms","快速排序",     "进阶",["算法","排序","快速排序","分治","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/merge-sort.html",             "algorithms","归并排序",     "进阶",["算法","排序","归并排序","分治","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/heap-sort.html",              "algorithms","堆排序",       "进阶",["算法","排序","堆排序","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/binary-search.html",          "algorithms","二分查找",     "基础",["算法","搜索","二分查找","基础"]),
    CrawlTarget("https://www.runoob.com/w3cnote/recursion.html",              "algorithms","递归算法",     "进阶",["算法","递归","分治","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/greedy-algorithm.html",       "algorithms","贪心算法",     "进阶",["算法","贪心","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/backtracking-algorithm.html", "algorithms","回溯算法",     "进阶",["算法","回溯","搜索","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/divide-and-conquer.html",     "algorithms","分治算法",     "进阶",["算法","分治","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/dynamic-programming.html",    "algorithms","动态规划",     "进阶",["算法","动态规划","DP","进阶"]),
    CrawlTarget("https://www.runoob.com/w3cnote/time-complexity.html",        "algorithms","时间复杂度",   "基础",["算法","复杂度","大O","基础"]),

    # ═══════════════ 数据结构（hit-alibaba GitHub）═══════════════
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Linked-List.html","algorithms","链表详解",   "进阶",["数据结构","链表","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Tree.html",       "algorithms","树与二叉树", "进阶",["数据结构","树","二叉树","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Hash-Table.html",  "algorithms","哈希表详解", "进阶",["数据结构","哈希表","进阶"]),

    # ═══════════════ 算法（hit-alibaba GitHub）═══════════════
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Sorting.html",     "algorithms","排序算法大全","进阶",["算法","排序","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/DP.html",          "algorithms","动态规划",   "进阶",["算法","动态规划","DP","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Random.html",      "algorithms","随机算法",   "进阶",["算法","随机","概率","进阶"]),

    # ═══════════════ 数据库（hit-alibaba GitHub）═══════════════
    CrawlTarget("https://hit-alibaba.github.io/interview/Server/db/DB-Index.html",     "databases","数据库索引详解","进阶",["数据库","索引","B+Tree","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/Server/db/Transaction.html",  "databases","事务与并发控制","进阶",["数据库","事务","ACID","锁","进阶"]),

    # ═══════════════ 数据库 ═══════════════
    CrawlTarget("https://www.runoob.com/mysql/mysql-tutorial.html",           "databases","MySQL基础",     "基础",["数据库","MySQL","SQL","基础"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-select-query.html",       "databases","SQL查询",       "基础",["数据库","SQL","SELECT","基础"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-where-clause.html",       "databases","WHERE条件",     "基础",["数据库","SQL","WHERE","基础"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-join.html",               "databases","JOIN连接",      "进阶",["数据库","SQL","JOIN","进阶"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-index.html",              "databases","索引优化",      "进阶",["数据库","索引","B-Tree","进阶"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-transaction.html",        "databases","事务管理",      "进阶",["数据库","事务","ACID","进阶"]),
    CrawlTarget("https://www.runoob.com/mysql/mysql-normalization.html",      "databases","数据库范式",    "进阶",["数据库","范式","设计","进阶"]),

    # ═══════════════ 计算机网络（runoob）═══════════════
    CrawlTarget("https://www.runoob.com/w3cnote/summary-of-network.html",           "software_eng","计算机网络概述",   "基础",["计算机网络","OSI","TCP/IP","基础"]),
    CrawlTarget("https://www.runoob.com/tcpip/tcpip-intro.html",                    "software_eng","TCPIP协议详解",   "基础",["计算机网络","TCP/IP","协议","基础"]),
    CrawlTarget("https://www.runoob.com/http/http-intro.html",                      "software_eng","HTTP协议详解",    "基础",["计算机网络","HTTP","协议","基础"]),
    CrawlTarget("https://www.runoob.com/http/http-messages.html",                   "software_eng","HTTP消息结构",    "基础",["计算机网络","HTTP","请求","响应","基础"]),

    # ═══════════════ 软件工程（维基教科书）═══════════════
    CrawlTarget("https://zh.wikibooks.org/wiki/软件工程",                           "software_eng","软件工程概论",     "基础",["软件工程","SDLC","基础"]),

    # ═══════════════ SpringBoot（廖雪峰 + CSDN）═══════════════
    CrawlTarget("https://blog.csdn.net/abjtxf/article/details/132410101",            "software_eng","SpringBoot入门详解","基础",["SpringBoot","Java","框架","入门","IoC","AOP","基础"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/package/index.html",  "software_eng","SpringBoot打包部署","基础",["SpringBoot","Maven","打包","部署","基础"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/profiles/index.html", "software_eng","SpringBoot多环境配置","进阶",["SpringBoot","Profile","配置","环境","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/conditional/index.html","software_eng","SpringBoot条件装配","进阶",["SpringBoot","Conditional","条件装配","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/configuration/index.html","software_eng","SpringBoot配置管理","基础",["SpringBoot","Configuration","配置","基础"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/filter/index.html",   "software_eng","SpringBoot过滤器","进阶",["SpringBoot","Filter","过滤器","Web","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/integration/open-api/index.html","software_eng","SpringBoot集成OpenAPI","进阶",["SpringBoot","OpenAPI","Swagger","文档","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/integration/redis/index.html","software_eng","SpringBoot集成Redis","进阶",["SpringBoot","Redis","缓存","集成","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/integration/rabbitmq/index.html","software_eng","SpringBoot集成RabbitMQ","进阶",["SpringBoot","RabbitMQ","消息队列","集成","进阶"]),
    CrawlTarget("https://liaoxuefeng.com/books/java/springboot/integration/kafka/index.html","software_eng","SpringBoot集成Kafka","进阶",["SpringBoot","Kafka","消息队列","集成","进阶"]),

    # ═══════════════ SpringBoot（springdoc.cn）═══════════════
    CrawlTarget("https://springdoc.cn/spring-boot/",                                "software_eng","SpringBoot概述", "基础",["SpringBoot","Java","框架","入门","基础"]),
    CrawlTarget("https://springdoc.cn/spring-ioc/",                                 "software_eng","Spring IoC容器", "进阶",["Spring","IoC","依赖注入","Bean","进阶"]),
    CrawlTarget("https://springdoc.cn/spring-aop/",                                 "software_eng","Spring AOP机制", "进阶",["Spring","AOP","切面","通知","进阶"]),
    CrawlTarget("https://springdoc.cn/spring-mvc/",                                 "software_eng","Spring MVC开发", "进阶",["SpringBoot","MVC","Web","REST","进阶"]),

    # ═══════════════ Maven / Gradle（runoob）═══════════════
    CrawlTarget("https://www.runoob.com/maven/maven-tutorial.html",                  "software_eng","Maven包管理",    "基础",["Maven","包管理","依赖","pom.xml","基础"]),

    # ═══════════════ MyBatis（mybatis.org 中文）═══════════════
    CrawlTarget("https://mybatis.org/mybatis-3/zh/getting-started.html",             "software_eng","MyBatis入门",   "基础",["MyBatis","ORM","SQL","Java","基础"]),

    # ═══════════════ Vue + Axios（runoob）═══════════════
    CrawlTarget("https://www.runoob.com/vue2/vue-tutorial.html",                     "software_eng","Vue基础教程",   "基础",["Vue","前端","组件","基础"]),
    CrawlTarget("https://www.runoob.com/vue2/vue-router.html",                       "software_eng","Vue路由守卫",   "进阶",["Vue","路由","导航守卫","进阶"]),
    CrawlTarget("https://www.runoob.com/vue2/vue-ajax.html",                         "software_eng","Vue+Axios联调", "进阶",["Vue","Axios","API","前后端","进阶"]),

    # ═══════════════ 数学 ═══════════════
    CrawlTarget("https://zh.wikibooks.org/wiki/高等数学",                      "math",     "微积分入门",     "基础",["数学","高等数学","微积分","极限","导数","基础"]),
    CrawlTarget("https://zh.wikibooks.org/wiki/线性代数",                      "math",     "线性代数",       "基础",["数学","线性代数","矩阵","向量","基础"]),
    CrawlTarget("https://zh.wikibooks.org/wiki/概率论",                        "math",     "概率论基础",     "基础",["数学","概率论","随机变量","基础"]),
]
# fmt: on


def crawl_page(target: CrawlTarget, dry_run: bool = False) -> str | None:
    """Fetch a page, extract main content, save as Markdown."""
    if dry_run:
        print(f"  [DRY-RUN] {target.subject}/{target.topic} ← {target.url}")
        return None

    print(f"  Fetching {target.url} ...")
    try:
        resp = requests.get(target.url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Remove noise ──
    for tag in soup.select(
        "script, style, nav, footer, .sidebar, .advertisement, "
        ".runoob-sidebar, .comments, #comments, .nav, .header-nav, "
        "#mw-navigation, #catlinks, .printfooter, #siteSub"
    ):
        tag.decompose()

    # ── Extract body ──
    body = _extract_body(soup, target)

    if not body or len(body) < 100:
        print(f"    WARNING: extracted content too short ({len(body)} chars)")
        return None

    # ── Build Markdown ──
    source_label = urlparse(target.url).netloc
    md = (
        f"# {target.topic}\n\n"
        f"> 来源: {target.url}\n"
        f"> 爬取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"> 学科: {target.subject} | 难度: {target.difficulty}\n"
        f"> 标签: {', '.join(target.tags)}\n\n"
        f"---\n\n"
        f"{body}\n"
    )

    # ── Save ──
    out_dir = CRAWLED_DIR / target.subject
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", target.topic)
    out_path = out_dir / f"{safe_name}.md"
    out_path.write_text(md, encoding="utf-8")

    print(f"    → Saved {out_path} ({len(md)} chars)")
    return str(out_path)


def _extract_body(soup: BeautifulSoup, target: CrawlTarget) -> str:
    """Extract main content from page, preferring known selectors."""
    # Try runoob.com content area first
    content_area = soup.select_one(
        ".article-body, .content, .main-content, "
        "#content, .mw-parser-output, article, main, "
        ".markdown-body, .post-content"
    )
    if content_area:
        return _html_to_markdown(content_area)

    # Fallback: use whole body minus header
    body = soup.find("body")
    if body:
        for h in body.select("header, .header, #header"):
            h.decompose()
        return _html_to_markdown(body)

    return ""


def _html_to_markdown(element: Any) -> str:
    """Convert BeautifulSoup element tree to clean Markdown text."""
    lines: list[str] = []

    for child in element.descendants:
        if not hasattr(child, "name") or child.name is None:
            continue

        text = child.get_text(strip=True) if hasattr(child, "get_text") else ""
        if not text:
            continue

        tag = child.name
        if tag in ("h1", "h2", "h3", "h4"):
            level = int(tag[1])
            lines.append(f"\n{'#' * level} {text}\n")
        elif tag == "p":
            lines.append(f"\n{text}\n")
        elif tag == "li":
            lines.append(f"- {text}")
        elif tag == "pre":
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "code" and child.parent.name != "pre":
            lines.append(f"`{text}`")
        elif tag == "strong":
            lines.append(f"**{text}**")
        elif tag == "em":
            lines.append(f"*{text}*")
        elif tag in ("table", "thead", "tbody", "tr", "td", "th"):
            pass  # skip table tags (inline text picked up elsewhere)
        elif tag in ("div", "section", "article", "span", "a"):
            pass  # skip container tags

    # Deduplicate and clean
    seen: set[str] = set()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            cleaned.append(line)

    return "\n".join(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl educational resources")
    parser.add_argument("--dry-run", action="store_true", help="List URLs without fetching")
    parser.add_argument("--subject", type=str, help="Crawl only one subject folder")
    args = parser.parse_args()

    targets = TARGETS
    if args.subject:
        targets = [t for t in TARGETS if t.subject == args.subject]

    print(f"Crawl targets: {len(targets)}")
    succeeded = 0
    for i, target in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {target.subject}/{target.topic}")
        path = crawl_page(target, dry_run=args.dry_run)
        if path:
            succeeded += 1
        if not args.dry_run and i < len(targets):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\nDone. Succeeded: {succeeded}/{len(targets)}")
    if succeeded:
        print(f"Files saved to: {CRAWLED_DIR}")


if __name__ == "__main__":
    main()
