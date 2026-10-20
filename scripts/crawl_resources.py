#!/usr/bin/env python3
"""Crawl educational resources from runoob.com and wikibooks.

Usage:
    python scripts/crawl_resources.py               # crawl all configured URLs
    python scripts/crawl_resources.py --dry-run     # list URLs without fetching
    python scripts/crawl_resources.py --subject python  # crawl one subject only
"""

from __future__ import annotations

import argparse
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_DIR = Path(__file__).resolve().parent.parent
from common.knowledge_paths import CORPUS_DIR

CRAWLED_DIR = CORPUS_DIR
CRAWLED_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "PersonalizedLearningKnowledgeBot/1.0 (educational RAG indexer)"
}

REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.5  # seconds — be polite

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
    ),
)
ROBOTS_CACHE: dict[str, RobotFileParser | None] = {}


def _robots_allowed(url: str) -> bool:
    """Respect robots.txt; an unavailable robots file is recorded as no policy."""

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in ROBOTS_CACHE:
        robots_url = urljoin(origin, "/robots.txt")
        try:
            response = SESSION.get(robots_url, timeout=min(REQUEST_TIMEOUT, 10))
            if response.status_code == 200:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                ROBOTS_CACHE[origin] = parser
            else:
                ROBOTS_CACHE[origin] = None
        except requests.RequestException:
            ROBOTS_CACHE[origin] = None
    policy = ROBOTS_CACHE[origin]
    return True if policy is None else policy.can_fetch(HEADERS["User-Agent"], url)


# ── URL Configuration ──────────────────────────────────────────────
@dataclass
class CrawlTarget:
    url: str
    subject: str
    topic: str
    difficulty: str = "基础"
    tags: list[str] = field(default_factory=list)
    university: str = ""
    course: str = ""
    author: str = ""
    license: str = "source-terms"
    language: str = "zh-CN"
    source_type: str = "documentation"
    crawl_scope: str = "public-page"


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
    CrawlTarget("https://docs.python.org/zh-cn/3/reference/compound_stmts.html", "python", "Python装饰器与异步函数", "进阶", ["Python","装饰器","async","await","协程","进阶"]),
    CrawlTarget("https://docs.python.org/zh-cn/3/tutorial/datastructures.html", "python", "Python数据结构进阶", "进阶", ["Python","列表推导式","字典","栈","队列","进阶"]),

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
    CrawlTarget("https://www.runoob.com/data-structures/data-structures-tutorial.html", "data_structures","数据结构概述","基础",["数据结构","入门","基础"]),
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
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Linked-List.html","data_structures","链表详解",   "进阶",["数据结构","链表","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Tree.html",       "data_structures","树与二叉树", "进阶",["数据结构","树","二叉树","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Hash-Table.html",  "data_structures","哈希表详解", "进阶",["数据结构","哈希表","进阶"]),

    # ═══════════════ 算法（hit-alibaba GitHub）═══════════════
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Sorting.html",     "algorithms","排序算法大全","进阶",["算法","排序","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/DP.html",          "algorithms","动态规划",   "进阶",["算法","动态规划","DP","进阶"]),
    CrawlTarget("https://hit-alibaba.github.io/interview/basic/algo/Random.html",      "algorithms","随机算法",   "进阶",["算法","随机","概率","进阶"]),
    CrawlTarget("https://oi-wiki.org/graph/shortest-path/",                           "algorithms","最短路算法", "进阶",["图论","最短路","最短路径","Dijkstra","Floyd","Bellman-Ford","进阶"]),
    CrawlTarget("https://oi-wiki.org/ds/dsu/",                                       "data_structures","并查集",       "进阶",["数据结构","并查集","路径压缩","集合","进阶"]),
    CrawlTarget("https://oi-wiki.org/graph/bi-graph/",                               "algorithms","二分图判定",   "进阶",["图论","二分图","二部图","BFS","DFS","进阶"]),

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
    CrawlTarget("https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html",  "databases","InnoDB锁与并发控制", "进阶",["数据库","MySQL","InnoDB","乐观锁","悲观锁","行锁","进阶"]),
    CrawlTarget("https://zh.wikipedia.org/wiki/数据库规范化",                  "databases","数据库规范化",  "进阶",["数据库","范式","1NF","2NF","3NF","BCNF","进阶"]),
    CrawlTarget("https://zh.wikipedia.org/wiki/乐观并发控制",                  "databases","乐观并发控制",  "进阶",["数据库","乐观锁","版本号","并发控制","进阶"]),
    CrawlTarget("https://zh.wikipedia.org/wiki/悲观并发控制",                  "databases","悲观并发控制",  "进阶",["数据库","悲观锁","行锁","并发控制","进阶"]),

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

    # ═══════════════ 大学公开课程页面（只采集公开课程页，不绕过登录或付费限制）═══════════════
    CrawlTarget("https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/", "python", "MIT计算机科学与Python程序设计", "基础", ["Python","计算思维","课程大纲","大学公开课"], "Massachusetts Institute of Technology", "6.0001 Introduction to Computer Science and Programming in Python", "Ana Bell; Eric Grimson; John Guttag", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/", "algorithms", "MIT算法导论", "进阶", ["算法","数据结构","复杂度","大学公开课"], "Massachusetts Institute of Technology", "6.006 Introduction to Algorithms", "Erik Demaine; Srini Devadas", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-fall-2010/", "discrete_math", "MIT计算机科学数学", "进阶", ["离散数学","逻辑","证明","图论","概率","大学公开课"], "Massachusetts Institute of Technology", "6.042J Mathematics for Computer Science", "Tom Leighton; Marten van Dijk", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-034-artificial-intelligence-fall-2010/", "artificial_intelligence", "MIT人工智能导论", "进阶", ["人工智能","搜索","知识表示","机器学习","大学公开课"], "Massachusetts Institute of Technology", "6.034 Artificial Intelligence", "Patrick Henry Winston", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://fa26.datastructur.es/", "data_structures", "Berkeley数据结构课程", "基础", ["数据结构","链表","树","哈希表","图","Java","大学公开课"], "University of California, Berkeley", "CS 61B Data Structures", "UC Berkeley CS 61B instructors", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://web.stanford.edu/class/cs166/", "data_structures", "Stanford高级数据结构", "进阶", ["数据结构","摊还分析","随机化","平衡树","持久化数据结构","大学公开课"], "Stanford University", "CS 166 Data Structures", "Keith Schwarz", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://www.cs.cmu.edu/~15122-archive/n26/handouts.shtml", "data_structures", "CMU数据结构课程资料", "基础", ["数据结构","栈","队列","链表","数组","哈希","大学公开课"], "Carnegie Mellon University", "15-122 Principles of Imperative Computation", "CMU School of Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-004-computation-structures-spring-2009/", "computer_architecture", "MIT计算结构与计算机组成", "进阶", ["计算机组成原理","数字逻辑","指令集","CPU","流水线","存储层次","大学公开课"], "Massachusetts Institute of Technology", "6.004 Computation Structures", "Steve Ward", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://notes.cs61c.org/", "computer_architecture", "Berkeley计算机体系结构课程笔记", "进阶", ["计算机组成原理","RISC-V","汇编","CPU","缓存","并行计算","大学公开课"], "University of California, Berkeley", "CS 61C Great Ideas in Computer Architecture", "Lisa Yan; UC Berkeley CS 61C instructors", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://pdos.csail.mit.edu/6.1810/2024/", "operating_systems", "MIT操作系统工程", "进阶", ["操作系统","xv6","进程","虚拟内存","文件系统","大学公开课"], "Massachusetts Institute of Technology", "6.1810 Operating System Engineering", "MIT PDOS", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-828-operating-system-engineering-fall-2012/pages/syllabus/", "operating_systems", "MIT操作系统工程课程大纲", "进阶", ["操作系统","内核","进程","线程","虚拟内存","系统调用","大学公开课"], "Massachusetts Institute of Technology", "6.828 Operating System Engineering", "Frans Kaashoek; Robert Morris", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-828-operating-system-engineering-fall-2012/pages/study-materials/", "operating_systems", "MIT_xv6操作系统学习资料", "进阶", ["操作系统","xv6","Unix","并发","文件系统","内核"], "Massachusetts Institute of Technology", "6.828 Operating System Engineering", "Frans Kaashoek; Robert Morris", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://pdos.csail.mit.edu/6.824/schedule.html", "distributed_systems", "MIT分布式系统", "进阶", ["分布式系统","一致性","容错","Raft","大学公开课"], "Massachusetts Institute of Technology", "6.5840 Distributed Systems", "MIT PDOS", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://www.cs.cmu.edu/afs/cs/academic/class/15213-s25/www/schedule.html", "computer_systems", "CMU计算机系统导论", "进阶", ["计算机系统","内存","汇编","并发","网络","大学公开课"], "Carnegie Mellon University", "15-213 Introduction to Computer Systems", "CMU School of Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://courseweb.sp.cs.cmu.edu/", "distributed_systems", "CMU分布式系统课程", "进阶", ["分布式系统","并发","容错","项目","大学公开课"], "Carnegie Mellon University", "15-440 Distributed Systems", "CMU School of Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://inst.eecs.berkeley.edu/~cs186/", "databases", "Berkeley数据库系统导论", "进阶", ["数据库","事务","查询优化","存储","大学公开课"], "University of California, Berkeley", "CS 186 Introduction to Database Systems", "UC Berkeley EECS", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://inst.eecs.berkeley.edu/~cs188/", "artificial_intelligence", "Berkeley人工智能导论", "进阶", ["人工智能","搜索","概率","机器学习","大学公开课"], "University of California, Berkeley", "CS 188 Introduction to Artificial Intelligence", "UC Berkeley EECS", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://cs144.github.io/", "computer_networks", "Stanford计算机网络", "进阶", ["计算机网络","TCP","路由","网络协议","大学公开课"], "Stanford University", "CS 144 Introduction to Computer Networking", "Stanford Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://www.cs.princeton.edu/courses/archive/spr20/cos461/syllabus.html", "computer_networks", "Princeton计算机网络课程", "进阶", ["计算机网络","链路层","IP","路由","TCP","DNS","网络安全","大学公开课"], "Princeton University", "COS 461 Computer Networks", "Michael Freedman; Jennifer Rexford", "CC BY-NC-SA 3.0", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://cs229.stanford.edu/", "machine_learning", "Stanford机器学习", "进阶", ["机器学习","监督学习","无监督学习","优化","大学公开课"], "Stanford University", "CS 229 Machine Learning", "Stanford Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://cs231n.stanford.edu/", "deep_learning", "Stanford视觉深度学习", "进阶", ["深度学习","计算机视觉","神经网络","CNN","大学公开课"], "Stanford University", "CS 231n Deep Learning for Computer Vision", "Stanford Computer Science", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://cs161.org/", "cybersecurity", "Berkeley计算机安全", "进阶", ["信息安全","密码学","系统安全","网络安全","大学公开课"], "University of California, Berkeley", "CS 161 Computer Security", "UC Berkeley EECS", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://cs50.harvard.edu/x/", "computer_science", "Harvard CS50计算机科学导论", "基础", ["计算机科学","C语言","Python","SQL","Web","大学公开课"], "Harvard University", "CS50x Introduction to Computer Science", "David J. Malan; Harvard CS50", "CC BY-NC-SA 4.0", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "linear_algebra", "MIT线性代数", "基础", ["线性代数","矩阵","向量空间","特征值","大学公开课"], "Massachusetts Institute of Technology", "18.06 Linear Algebra", "Gilbert Strang", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-035-computer-language-engineering-spring-2010/", "compilers", "MIT编译原理", "进阶", ["编译原理","词法分析","语法分析","代码生成","大学公开课"], "Massachusetts Institute of Technology", "6.035 Computer Language Engineering", "MIT EECS", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://ocw.mit.edu/courses/6-041sc-probabilistic-systems-analysis-and-applied-probability-fall-2013/", "probability", "MIT概率系统分析", "进阶", ["概率论","随机变量","贝叶斯","随机过程","大学公开课"], "Massachusetts Institute of Technology", "6.041SC Probabilistic Systems Analysis", "John Tsitsiklis; Patrick Jaillet", "CC BY-NC-SA", "en", "open-courseware", "public-course-page"),
    CrawlTarget("https://fullstackopen.com/en/", "web_development", "Helsinki全栈开发公开课", "进阶", ["Web开发","React","Node.js","GraphQL","TypeScript","大学公开课"], "University of Helsinki", "Full Stack Open", "University of Helsinki", "source-terms", "en", "public-course", "public-course-page"),
    CrawlTarget("https://missing.csail.mit.edu/", "developer_tools", "MIT计算机教育中缺失的一课", "基础", ["Shell","Git","调试","命令行","开发工具","大学公开课"], "Massachusetts Institute of Technology", "The Missing Semester of Your CS Education", "MIT CSAIL", "CC BY-NC-SA 4.0", "en", "open-courseware", "public-course-page"),
]
# fmt: on


def _output_path(target: CrawlTarget) -> Path:
    safe_name = re.sub(r"[^\w\-]", "_", target.topic)
    return CRAWLED_DIR / target.subject / f"{safe_name}.md"


def crawl_page(
    target: CrawlTarget,
    dry_run: bool = False,
    *,
    skip_existing: bool = False,
) -> str | None:
    """Fetch a page, extract main content, save as Markdown."""
    out_path = _output_path(target)
    if skip_existing and out_path.exists() and out_path.stat().st_size >= 500:
        print(f"  [SKIP] {target.subject}/{target.topic} already exists")
        return str(out_path)
    if dry_run:
        print(f"  [DRY-RUN] {target.subject}/{target.topic} ← {target.url}")
        return None

    if not _robots_allowed(target.url):
        print(f"  [SKIP robots.txt] {target.url}")
        return None

    print(f"  Fetching {target.url} ...")
    try:
        resp = SESSION.get(target.url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # All configured documentation sources currently serve UTF-8.  Decoding
        # the bytes explicitly avoids requests/chardet mistaking short Chinese
        # pages for a Western encoding and persisting mojibake in the corpus.
        try:
            html = resp.content.decode("utf-8")
        except UnicodeDecodeError:
            html = resp.content.decode(resp.apparent_encoding or "utf-8", errors="replace")
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None

    try:
        content_type = resp.headers.get("Content-Type", "").casefold()
        suffix = Path(urlparse(target.url).path).suffix.casefold()
        if suffix == ".pdf" or "application/pdf" in content_type:
            body = _pdf_to_markdown(resp.content)
        elif suffix in {".md", ".txt"} or content_type.startswith("text/plain"):
            body = html.strip()
        else:
            soup = BeautifulSoup(html, "html.parser")

            # ── Remove noise ──
            for tag in soup.select(
                "script, style, nav, footer, .sidebar, .advertisement, "
                ".runoob-sidebar, .comments, #comments, .nav, .header-nav, "
                "#mw-navigation, #catlinks, .printfooter, #siteSub"
            ):
                tag.decompose()

            # ── Extract body ──
            body = _extract_body(soup, target)
    except Exception as exc:
        print(f"    ERROR extracting content: {exc}")
        return None

    if not body or len(body) < 100:
        print(f"    WARNING: extracted content too short ({len(body)} chars)")
        return None

    # ── Build Markdown ──
    md = render_document(target, body)

    # ── Save ──
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_suffix(out_path.suffix + ".tmp")
    temporary.write_text(md, encoding="utf-8")
    temporary.replace(out_path)

    print(f"    → Saved {out_path} ({len(md)} chars)")
    return str(out_path)


def render_document(
    target: CrawlTarget,
    body: str,
    *,
    crawled_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """Render one normalized, provenance-rich corpus document."""

    source_label = urlparse(target.url).netloc
    timestamp = crawled_at or datetime.now(UTC).isoformat()
    update_timestamp = updated_at or datetime.now(UTC).isoformat()
    document_id = hashlib.sha256(target.url.encode("utf-8")).hexdigest()[:20]
    normalized_body = "\n".join(
        line.rstrip() for line in body.replace("\r", "").splitlines()
    ).strip()
    content_hash = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    md = (
        f"# {target.topic}\n\n"
        f"> 文档ID: {document_id}\n"
        f"> 来源: {target.url}\n"
        f"> 来源站点: {source_label}\n"
        f"> 来源类型: {target.source_type}\n"
        f"> 大学: {target.university or '未标注'}\n"
        f"> 课程: {target.course or target.topic}\n"
        f"> 作者或机构: {target.author or source_label}\n"
        f"> 授权: {target.license}\n"
        f"> 采集范围: {target.crawl_scope}\n"
        f"> 语言: {target.language}\n"
        f"> 爬取时间: {timestamp}\n"
        f"> 更新时间: {update_timestamp}\n"
        f"> 内容哈希: {content_hash}\n"
        f"> 学科: {target.subject} | 难度: {target.difficulty}\n"
        f"> 标签: {', '.join(target.tags)}\n\n"
        f"---\n\n"
        f"{normalized_body}\n"
    )
    return md


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


def _pdf_to_markdown(content: bytes) -> str:
    """Extract text from a bounded, publicly accessible PDF response."""

    if len(content) > 25 * 1024 * 1024:
        raise ValueError("PDF exceeds the 25 MB crawler limit")
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages[:300], 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"## 第 {page_number} 页\n\n{text}")
    return "\n\n".join(pages)


def _html_to_markdown(element: Any) -> str:
    """Convert semantic block elements to Markdown without nested-text duplication."""
    lines: list[str] = []

    block_tags = {"h1", "h2", "h3", "h4", "p", "li", "pre", "table", "blockquote"}
    for child in element.find_all(block_tags):
        if not isinstance(child, Tag):
            continue
        if child.find_parent(block_tags):
            continue

        text = re.sub(r"\s+", " ", child.get_text(" ", strip=True)).strip()
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
            code = child.get_text("\n", strip=True)
            lines.append(f"\n```\n{code}\n```\n")
        elif tag == "blockquote":
            lines.append("\n" + "\n".join(f"> {line}" for line in text.splitlines()) + "\n")
        elif tag == "table":
            rows = []
            for row in child.find_all("tr"):
                cells = [
                    re.sub(r"\s+", " ", cell.get_text(" ", strip=True))
                    for cell in row.find_all(["th", "td"])
                ]
                if cells:
                    rows.append(cells)
            if rows:
                width = max(len(row) for row in rows)
                normalized = [row + [""] * (width - len(row)) for row in rows]
                lines.append("\n| " + " | ".join(normalized[0]) + " |")
                lines.append("| " + " | ".join(["---"] * width) + " |")
                lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
                lines.append("")

    # Deduplicate and clean
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and (not cleaned or cleaned[-1].strip() != stripped):
            cleaned.append(line)

    return "\n".join(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl educational resources")
    parser.add_argument("--dry-run", action="store_true", help="List URLs without fetching")
    parser.add_argument("--subject", type=str, help="Crawl only one subject folder")
    parser.add_argument(
        "--university-only",
        action="store_true",
        help="Crawl only configured university course sources",
    )
    parser.add_argument(
        "--topic",
        action="append",
        help="Crawl only this topic; repeat the option to select multiple topics",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Only fetch targets that do not already have a usable Markdown file",
    )
    args = parser.parse_args()

    targets = TARGETS
    if args.subject:
        targets = [t for t in TARGETS if t.subject == args.subject]
    if args.university_only:
        targets = [t for t in targets if t.university]
    if args.topic:
        wanted_topics = set(args.topic)
        targets = [t for t in targets if t.topic in wanted_topics]

    print(f"Crawl targets: {len(targets)}")
    succeeded = 0
    for i, target in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {target.subject}/{target.topic}")
        path = crawl_page(target, dry_run=args.dry_run, skip_existing=args.skip_existing)
        if path:
            succeeded += 1
        if not args.dry_run and i < len(targets):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\nDone. Succeeded: {succeeded}/{len(targets)}")
    if succeeded:
        print(f"Files saved to: {CRAWLED_DIR}")


if __name__ == "__main__":
    main()
