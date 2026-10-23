"""Supplement the demo role accounts so every scope point has sufficient evidence.

Gap this script closes (2026-10-23 audit of runtime.sqlite)
------------------------------------------------------------
The 4 demo teaching classes with knowledge-point scopes cover 18 scope points,
but only ``冒泡排序`` (clones of 数据结构) and ``UDP`` (clones of 计算机网络)
had demo questions and therefore sufficient evidence (10 answers per student).
The other 16 points had **zero** exercises, so every student's evidence on them
was ``no_evidence``.

What this script does
---------------------
Phase A (bank, idempotent)   : author 10 objective demo questions per missing
                               scope point (choice/judge/blank only — zero model
                               calls). Environment prep only; no answer rows.
Phase B (answers, real)      : every demo student logs in over HTTP and answers
                               up to 10 distinct demo questions per scope point
                               via ``POST /evaluation/batch_submit``. Grading is
                               done by the service (standard-answer comparison);
                               the script never writes mastery / correct rates.
Phase C (verify)             : per (student, scope point) assert
                               ``load_evidence`` → ``summarize`` is sufficient
                               (>= 8 distinct questions) with a non-null mastery,
                               teacher insights expose differentiated mastery via
                               the real API, and the excellent persona outranks
                               the struggling persona.

    python scripts/demo_supplement_evidence.py --db artifacts/local-start-20261019/runtime.sqlite
    python scripts/demo_supplement_evidence.py --db <db> --skip-bank   # answers + verify only
    python scripts/demo_supplement_evidence.py --db <db> --verify-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import requests  # noqa: E402
from demo_role_use_cases import (  # noqa: E402
    DEFAULT_QUESTIONS_PER_STUDENT,
    EVAL_API,
    PERSONA_ACCURACY,
    TEACHER_API,
    USER_API,
    TZ,
    _answer_payload,
    _ratio,
)
from demo_teaching_dataset import DEFAULT_PASSWORD, STUDENTS, configure_database  # noqa: E402

# 本机会话可能配置了 HTTP(S)_PROXY：所有请求必须直连本地服务，绕过代理。
HTTP = requests.Session()
HTTP.trust_env = False
HTTP.proxies = {"http": None, "https": None}
REQUEST_TIMEOUT = 300

AUTHORED_KEY_PREFIX = "demo-authored-"
DEMO_KEY_GLOB = "demo-%"
CLASS_SCOPE_MIN = 10

USER_API_BASE = USER_API


# --------------------------------------------------------------------------- #
# Phase A · authored demo question bank (environment prep, idempotent)
# --------------------------------------------------------------------------- #
# Each entry: (type, difficulty, prompt, options, answer, analysis)
# type ∈ choice / judge / blank. Answers must be exact strings for the
# server-side standard-answer comparison.
BANK: dict[tuple[str, str], list[tuple]] = {
    ("数据结构", "顺序表"): [
        ("choice", 1, "顺序表采用的存储结构是？", ["A. 随机存取的顺序存储", "B. 链式存储", "C. 索引存储", "D. 散列存储"], "A", "顺序表用一段连续存储单元存放元素，可按位随机存取。"),
        ("choice", 2, "长度为 n 的顺序表在第 i 个位置（1≤i≤n+1）插入元素，平均需移动的元素个数是？", ["A. n-i", "B. n-i+1", "C. i", "D. n/2"], "D", "平均移动次数为 n/2，等概率下各位置插入的移动次数取平均。"),
        ("choice", 1, "顺序表按下标查找元素的时间复杂度是？", ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n²)"], "A", "按下标可直接计算地址，随机存取为 O(1)。"),
        ("choice", 2, "删除长度为 n 的顺序表第 i 个元素需要移动多少个元素？", ["A. n-i", "B. n-i+1", "C. i", "D. n"], "A", "删除第 i 个元素后，其后 n-i 个元素需依次前移。"),
        ("judge", 1, "顺序表支持随机存取。", [], "正确", "顺序表按下标可直接定位，支持随机存取。"),
        ("judge", 2, "顺序表插入和删除都不需要移动元素。", [], "错误", "顺序表插入删除通常需要移动元素保持连续。"),
        ("judge", 2, "顺序表的存储密度高于链表。", [], "正确", "顺序表只存数据本身，链表还要存指针，存储密度更低。"),
        ("blank", 1, "长度为 n 的顺序表最后一个元素的下标（从 0 开始）是____。", [], "n-1", "下标从 0 开始时，最后一个元素下标为 n-1。"),
        ("blank", 2, "顺序表插入算法的平均时间复杂度是____。", [], "O(n)", "插入平均移动一半元素，时间复杂度 O(n)。"),
        ("blank", 1, "在长度为 n 的顺序表末尾（第 n+1 个位置）插入一个元素需移动____个元素。", [], "0", "末尾插入不影响已有元素，移动 0 个。"),
    ],
    ("数据结构", "链表"): [
        ("choice", 2, "在单链表中，结点 p 之后插入结点 s 的正确操作是？", ["A. s->next=p->next; p->next=s", "B. p->next=s; s->next=p->next", "C. s->next=p; p=s", "D. p->next=s->next"], "A", "必须先接后断，否则会丢失 p 原来的后继。"),
        ("choice", 2, "删除单链表中结点 p 的后继结点 q 的正确操作是？", ["A. p->next=q->next", "B. q->next=p->next", "C. p=q->next", "D. q->next=NULL"], "A", "让 p 的 next 指向 q 的后继即可摘除 q。"),
        ("choice", 1, "带头结点的单链表为空的判定条件是？", ["A. head==NULL", "B. head->next==NULL", "C. head->next==head", "D. head==head->next"], "B", "带头结点时头结点始终存在，判空看 head->next。"),
        ("choice", 1, "访问单链表第 i 个结点的时间复杂度是？", ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n log n)"], "C", "链表不支持随机存取，须从头顺序查找。"),
        ("judge", 1, "双链表既可以向前也可以向后遍历。", [], "正确", "双链表结点含前驱、后继两个指针。"),
        ("judge", 2, "单链表支持随机存取。", [], "错误", "单链表只能顺序访问，不支持随机存取。"),
        ("judge", 1, "循环单链表中尾结点的 next 指向头结点。", [], "正确", "循环链表的尾结点指针回指形成环。"),
        ("blank", 1, "单链表的头指针指向____结点。", [], "头", "头指针指向链表的头结点（或第一个结点）。"),
        ("blank", 1, "单链表的结点由数据域和____域两部分组成。", [], "指针", "链表结点=数据域+指针域。"),
        ("blank", 2, "双链表的每个结点包含两个指针域，分别指向后继和____。", [], "前驱", "双链表结点含 next 与 prior 两个指针。"),
    ],
    ("数据结构", "栈"): [
        ("choice", 1, "栈的操作特性是？", ["A. 先进先出", "B. 后进先出", "C. 随机存取", "D. 优先级出栈"], "B", "栈是限定在栈顶进行插入删除的线性表，后进先出。"),
        ("choice", 3, "入栈序列为 1,2,3，下列不可能的出栈序列是？", ["A. 1,2,3", "B. 3,2,1", "C. 2,1,3", "D. 3,1,2"], "D", "3 先出说明 1、2 都在栈中，随后只能 2 先出，3,1,2 不可能。"),
        ("choice", 1, "表达式求值和函数调用通常借助的数据结构是？", ["A. 队列", "B. 栈", "C. 二叉树", "D. 哈希表"], "B", "表达式求值、函数调用、递归都利用栈的后进先出特性。"),
        ("choice", 2, "顺序栈 top 指向栈顶元素位置时，栈空的判定条件是？", ["A. top==0", "B. top==-1", "C. top==1", "D. top==maxsize"], "B", "约定 top=-1 表示空栈，top=0 表示栈底有第一个元素。"),
        ("judge", 1, "栈只能在栈顶进行插入和删除操作。", [], "正确", "栈限定在栈顶一端操作。"),
        ("judge", 1, "函数的嵌套调用利用了栈的后进先出特性。", [], "正确", "调用栈按后进先出保存返回地址与局部状态。"),
        ("judge", 2, "两个栈共享一个存储空间可以提高空间的利用率。", [], "正确", "两栈栈顶相向增长，可互相调剂剩余空间。"),
        ("blank", 1, "栈的插入操作称为____。", [], "入栈", "栈的插入称为入栈（push）。"),
        ("blank", 1, "栈的删除操作称为____。", [], "出栈", "栈的删除称为出栈（pop）。"),
        ("blank", 1, "递归函数的实现依赖____结构保存返回地址。", [], "栈", "递归调用由调用栈支撑。"),
    ],
    ("数据结构", "二叉搜索树"): [
        ("choice", 1, "对二叉搜索树进行中序遍历得到的序列是？", ["A. 递减序列", "B. 递增序列", "C. 无序序列", "D. 层次序列"], "B", "二叉搜索树的中序遍历是递增有序序列。"),
        ("choice", 2, "含 n 个结点的平衡二叉搜索树查找的时间复杂度是？", ["A. O(1)", "B. O(log n)", "C. O(n)", "D. O(n²)"], "B", "平衡时树高为 O(log n)，查找复杂度同阶。"),
        ("choice", 2, "向二叉搜索树插入新结点时，新结点总是成为？", ["A. 根结点", "B. 叶子结点", "C. 内部结点", "D. 任意位置"], "B", "插入总是沿着比较路径走到空指针处，成为新叶子。"),
        ("choice", 3, "删除二叉搜索树中具有两个孩子结点的结点，通常用谁替代它？", ["A. 左子树中最大结点或右子树中最小结点", "B. 直接删除整个子树", "C. 随机孩子提升", "D. 根结点替代"], "A", "用中序前驱或中序后继替代可保持 BST 性质。"),
        ("judge", 1, "二叉搜索树中左子树上所有结点的值都小于根结点的值。", [], "正确", "这是二叉搜索树的基本性质。"),
        ("judge", 2, "二叉搜索树退化为链表形状时查找退化为 O(n)。", [], "正确", "插入有序序列会使 BST 变成单支树。"),
        ("judge", 2, "二叉搜索树的中序遍历序列可能递减。", [], "错误", "中序遍历一定递增。"),
        ("blank", 1, "二叉搜索树中任一结点的左子树结点值均____该结点的值。", [], "小于", "BST 性质：左<根<右。"),
        ("blank", 2, "二叉搜索树中删除只有一个孩子的结点时，用其____接替该结点。", [], "孩子", "单孩子结点删除即用孩子顶替。"),
        ("blank", 2, "二叉搜索树中查找从根出发，每步与目标值比较后最多访问____个子树。", [], "一", "比较后只走向左或右一个子树。"),
    ],
    ("数据结构", "二叉树遍历"): [
        ("choice", 1, "前序遍历的访问顺序是？", ["A. 根、左、右", "B. 左、根、右", "C. 左、右、根", "D. 自上而下逐层"], "A", "前序=根左右。"),
        ("choice", 1, "中序遍历的访问顺序是？", ["A. 根、左、右", "B. 左、根、右", "C. 左、右、根", "D. 根、右、左"], "B", "中序=左根右。"),
        ("choice", 2, "由前序序列和中序序列确定二叉树时，前序序列的第一个结点是？", ["A. 根结点", "B. 叶结点", "C. 最左结点", "D. 任意结点"], "A", "前序第一个访问的是根。"),
        ("choice", 2, "n 个结点的二叉树中共有多少个空指针（孩子域）？", ["A. n-1", "B. n+1", "C. 2n", "D. n"], "B", "2n 个孩子域中用了 n-1 个，空指针为 n+1 个。"),
        ("judge", 1, "后序遍历中根结点最后被访问。", [], "正确", "后序=左右根。"),
        ("judge", 2, "层次遍历需要借助栈来实现。", [], "错误", "层次遍历借助队列实现。"),
        ("judge", 2, "任意二叉树中，叶子结点数比度为 2 的结点数多 1。", [], "正确", "n0 = n2 + 1 是二叉树的性质。"),
        ("blank", 2, "二叉树第 i 层（i≥1）最多有____个结点。", [], "2^(i-1)", "二叉树每层结点数最多翻倍。"),
        ("blank", 2, "高度为 h 的二叉树最多有____个结点。", [], "2^h-1", "满二叉树结点数为 2^h - 1。"),
        ("blank", 1, "后序遍历的顺序是左、右、____。", [], "根", "后序遍历最后访问根结点。"),
    ],
    ("数据结构", "图的遍历"): [
        ("choice", 1, "深度优先遍历（DFS）借助的辅助数据结构是？", ["A. 队列", "B. 栈", "C. 堆", "D. 散列表"], "B", "DFS 类似树的先根遍历，借助栈（或递归）。"),
        ("choice", 1, "广度优先遍历（BFS）借助的辅助数据结构是？", ["A. 栈", "B. 队列", "C. 优先队列", "D. 双链表"], "B", "BFS 逐层访问，借助队列。"),
        ("choice", 2, "对非连通无向图执行一次遍历调用，调用次数等于？", ["A. 连通分量个数", "B. 边数", "C. 顶点度数", "D. 顶点数"], "A", "每个连通分量需调用一次遍历。"),
        ("choice", 2, "用邻接表存储、含 n 个顶点 e 条边的图，DFS 的时间复杂度是？", ["A. O(n)", "B. O(n+e)", "C. O(n²)", "D. O(e²)"], "B", "邻接表遍历每个顶点与每条边各一次。"),
        ("judge", 2, "对无权图，BFS 可以求出单源最短路径。", [], "正确", "BFS 按层扩展，先到即最少边数路径。"),
        ("judge", 1, "DFS 使用队列作为辅助结构。", [], "错误", "DFS 用栈，BFS 用队列。"),
        ("judge", 1, "图遍历开始前需要把所有顶点标记为未访问。", [], "正确", "访问标记防止顶点被重复访问。"),
        ("blank", 1, "图的遍历要求每个顶点恰好被访问____次。", [], "一", "遍历的定义是每顶点访问一次。"),
        ("blank", 2, "BFS 生成树中，从源点到各顶点的路径是边数____的路径。", [], "最少", "BFS 按层扩展得到最少边数路径。"),
        ("blank", 1, "深度优先遍历类似于二叉树的____序遍历。", [], "先根", "DFS 沿分支深入，与先根遍历类似。"),
    ],
    ("数据结构", "最短路径"): [
        ("choice", 2, "Dijkstra 算法适用于求解？", ["A. 边权非负的图的单源最短路径", "B. 任意带负权图", "C. 无向树的直径", "D. 二分图匹配"], "A", "Dijkstra 基于贪心，要求边权非负。"),
        ("choice", 2, "用邻接矩阵实现 Dijkstra 算法的时间复杂度是？", ["A. O(n)", "B. O(n²)", "C. O(n log n)", "D. O(e log n)"], "B", "每次选最近顶点需扫描全部顶点。"),
        ("choice", 3, "图中存在负权边时，求单源最短路径应选用？", ["A. Dijkstra", "B. Bellman-Ford", "C. Prim", "D. Kruskal"], "B", "Bellman-Ford 能处理负权边并检测负环。"),
        ("choice", 1, "Floyd 算法求解的问题是？", ["A. 单源最短路径", "B. 每对顶点之间的最短路径", "C. 最小生成树", "D. 拓扑排序"], "B", "Floyd 是多源最短路径算法。"),
        ("judge", 2, "Dijkstra 算法基于贪心策略。", [], "正确", "每步选取当前距离最小的顶点。"),
        ("judge", 2, "Floyd 算法的时间复杂度是 O(n³)。", [], "正确", "三重循环枚举中转顶点。"),
        ("judge", 3, "Dijkstra 算法可以正确处理带负权边的图。", [], "错误", "负权边会破坏贪心的正确性。"),
        ("blank", 2, "Dijkstra 算法按路径长度____的次序依次确定各顶点的最短路径。", [], "递增", "贪心按距离递增次序确定。"),
        ("blank", 2, "Floyd 算法的核心思想是逐步允许经过顶点____进行中转。", [], "k", "枚举中转点更新 dist[i][j]。"),
        ("blank", 3, "若图中存在权值和为负的回路，则某些最短路径____。", [], "不存在", "绕负回路可以无限缩短路径。"),
    ],
    ("数据结构", "快速排序"): [
        ("choice", 1, "快速排序的平均时间复杂度是？", ["A. O(n)", "B. O(n log n)", "C. O(n²)", "D. O(log n)"], "B", "快排平均 O(n log n)。"),
        ("choice", 1, "快速排序在最坏情况下的时间复杂度是？", ["A. O(n log n)", "B. O(n²)", "C. O(n)", "D. O(log n)"], "B", "划分极不平衡时退化为 O(n²)。"),
        ("choice", 3, "以首元素为枢轴时，快速排序最坏情况发生在？", ["A. 序列已经基本有序", "B. 随机排列", "C. 元素全部互异且随机", "D. 递归深度为 log n"], "A", "基本有序时每次划分极度不平衡。"),
        ("choice", 2, "快速排序空间开销主要来自？", ["A. 递归调用栈", "B. 辅助数组", "C. 堆结构", "D. 哈希表"], "A", "快排是原地划分，空间为递归栈 O(log n)。"),
        ("judge", 2, "快速排序是一种不稳定的排序算法。", [], "正确", "划分交换会改变相等元素的相对次序。"),
        ("judge", 2, "每趟快速排序结束后，至少有一个元素位于其最终排序位置上。", [], "正确", "枢轴元素落位即最终位置。"),
        ("judge", 1, "快速排序的平均性能在内部排序算法中位于前列。", [], "正确", "平均 O(n log n) 且常数因子小。"),
        ("blank", 1, "快速排序通过一个____元素将序列划分为两部分。", [], "枢轴", "快排按枢轴划分。"),
        ("blank", 2, "快速排序的空间复杂度取决于____的深度。", [], "递归", "递归栈深度决定空间。"),
        ("blank", 2, "为避免快排退化为最坏情况，可以____选取枢轴。", [], "随机", "随机化枢轴可避免有序输入退化。"),
    ],
    ("计算机网络", "OSI 七层模型"): [
        ("choice", 1, "OSI 参考模型共分为几层？", ["A. 4 层", "B. 5 层", "C. 7 层", "D. 6 层"], "C", "OSI 自下而上共 7 层。"),
        ("choice", 1, "传输层位于 OSI 模型的第几层？", ["A. 第 3 层", "B. 第 4 层", "C. 第 5 层", "D. 第 6 层"], "B", "自下而上第 4 层是传输层。"),
        ("choice", 1, "负责路由选择与分组转发的是？", ["A. 物理层", "B. 数据链路层", "C. 网络层", "D. 会话层"], "C", "网络层负责路由选择。"),
        ("choice", 2, "表示层的主要功能是？", ["A. 比特流传输", "B. 数据格式转换、加密与压缩", "C. 流量控制", "D. 进程到进程的通信"], "B", "表示层处理语法与语义的表示。"),
        ("judge", 1, "数据链路层的传输单元是帧。", [], "正确", "链路层将比特封装成帧。"),
        ("judge", 2, "网络层负责端到端的可靠数据传输。", [], "错误", "端到端可靠传输由传输层负责，网络层是逐跳转发。"),
        ("judge", 1, "物理层传输的基本单位是比特。", [], "正确", "物理层在介质上传送比特流。"),
        ("blank", 1, "OSI 模型中紧邻物理层之上的是____层。", [], "数据链路", "第二层是数据链路层。"),
        ("blank", 2, "OSI 模型中实现进程到进程通信的是____层。", [], "传输", "传输层提供端到端（进程级）通信。"),
        ("blank", 2, "OSI 模型中应用层的下一层是____层。", [], "表示", "第 6 层是表示层。"),
    ],
    ("计算机网络", "TCP/IP 四层模型"): [
        ("choice", 1, "TCP/IP 体系结构从下到上依次是？", ["A. 物理、链路、网络、传输、应用", "B. 网络接口、网际、传输、应用", "C. 链路、IP、TCP、HTTP", "D. 物理、数据链路、网络、应用"], "B", "TCP/IP 四层：网络接口层、网际层、传输层、应用层。"),
        ("choice", 1, "IP 协议属于 TCP/IP 模型的？", ["A. 应用层", "B. 传输层", "C. 网际层", "D. 网络接口层"], "C", "IP 是网际层的核心协议。"),
        ("choice", 2, "与 OSI 七层模型相比，TCP/IP 模型没有的层次是？", ["A. 传输层", "B. 网络层", "C. 会话层与表示层", "D. 应用层"], "C", "TCP/IP 把会话、表示层并入应用层。"),
        ("choice", 1, "HTTP 协议属于 TCP/IP 模型的？", ["A. 网际层", "B. 传输层", "C. 应用层", "D. 网络接口层"], "C", "HTTP 是应用层协议。"),
        ("judge", 1, "TCP/IP 的网际层大致对应 OSI 的网络层。", [], "正确", "网际层负责主机到主机的分组转发。"),
        ("judge", 2, "TCP/IP 模型中传输层只有 TCP 一种协议。", [], "错误", "传输层还有 UDP 等协议。"),
        ("judge", 2, "TCP/IP 模型对会话层和表示层作了明确的划分。", [], "错误", "TCP/IP 没有独立的会话层与表示层。"),
        ("blank", 1, "TCP/IP 模型的最底层是____层。", [], "网络接口", "最底层负责物理传输与帧封装。"),
        ("blank", 1, "TCP/IP 网际层的核心协议是____。", [], "IP", "网际层以 IP 协议为核心。"),
        ("blank", 2, "与 OSI 相比，TCP/IP 把上三层合并为____层。", [], "应用", "应用层合并了会话、表示、应用。"),
    ],
    ("计算机网络", "IP 地址"): [
        ("choice", 1, "IPv4 地址的长度是？", ["A. 16 位", "B. 32 位", "C. 64 位", "D. 128 位"], "B", "IPv4 为 32 位地址。"),
        ("choice", 1, "地址 192.168.1.1 属于哪一类地址？", ["A. A 类", "B. B 类", "C. C 类", "D. D 类"], "C", "首字节 192~223 为 C 类。"),
        ("choice", 1, "子网掩码 255.255.255.0 对应的前缀长度是？", ["A. /8", "B. /16", "C. /24", "D. /32"], "C", "连续 24 个 1 即 /24。"),
        ("choice", 1, "IPv6 地址的长度是？", ["A. 32 位", "B. 64 位", "C. 128 位", "D. 256 位"], "C", "IPv6 地址为 128 位。"),
        ("judge", 1, "127.0.0.1 是环回测试地址。", [], "正确", "127 网段用于本机回环测试。"),
        ("judge", 2, "私有地址可以直接在公共互联网上路由。", [], "错误", "私有地址需经 NAT 转换才能访问公网。"),
        ("judge", 1, "子网掩码用于区分 IP 地址中的网络位与主机位。", [], "正确", "掩码 1 的部分为网络位。"),
        ("blank", 1, "IP 地址由网络号和____号两部分组成。", [], "主机", "IP=网络号+主机号。"),
        ("blank", 2, "C 类地址的默认子网掩码是 255.255.255.____。", [], "0", "C 类默认掩码 /24。"),
        ("blank", 2, "主机位全为 1 的 IP 地址表示____地址。", [], "广播", "主机位全 1 为定向广播地址。"),
    ],
    ("计算机网络", "子网划分"): [
        ("choice", 3, "192.168.1.0/26 划分出的每个子网的可用主机数是？", ["A. 62", "B. 64", "C. 30", "D. 126"], "A", "主机位 6 位，2^6-2=62。"),
        ("choice", 2, "前缀 /26 对应的子网掩码是？", ["A. 255.255.255.0", "B. 255.255.255.128", "C. 255.255.255.192", "D. 255.255.255.224"], "C", "26 个 1 = 255.255.255.192。"),
        ("choice", 3, "把 10.0.0.0/8 划分为 /24 的子网，共可分出多少个？", ["A. 256", "B. 65536", "C. 1024", "D. 16"], "B", "借 16 位主机位，2^16=65536 个子网。"),
        ("choice", 2, "主机位为 n 位时，扣除网络地址与广播地址后的可用主机数是？", ["A. 2^n", "B. 2^n - 2", "C. 2^n - 1", "D. 2^(n-1)"], "B", "全 0 为网络地址、全 1 为广播地址，需扣除。"),
        ("judge", 2, "划分子网会使每个子网的可用主机数减少。", [], "正确", "借位划分子网占用主机位。"),
        ("judge", 2, "192.168.1.255/24 是广播地址，不能分配给主机。", [], "正确", "/24 下主机位全 1 为广播地址。"),
        ("judge", 3, "/30 子网的可用主机数是 2。", [], "正确", "主机位 2 位，2^2-2=2，常用于点对点链路。"),
        ("blank", 2, "子网掩码 255.255.255.240 的前缀长度是____。", [], "/28", "28 个 1 对应 240。"),
        ("blank", 2, "/25 子网的可用主机数是____。", [], "126", "主机位 7 位，2^7-2=126。"),
        ("blank", 3, "把 /24 网络再借 2 位主机位划分子网，可以分出____个子网。", [], "4", "2^2=4 个子网。"),
    ],
    ("计算机网络", "TCP 三次握手"): [
        ("choice", 1, "TCP 建立连接的三次握手顺序是？", ["A. SYN → SYN+ACK → ACK", "B. SYN → ACK → SYN", "C. ACK → SYN → SYN+ACK", "D. SYN → FIN → ACK"], "A", "客户端 SYN，服务端 SYN+ACK，客户端 ACK。"),
        ("choice", 1, "第一次握手的报文中，SYN 标志位的值是？", ["A. 0", "B. 1", "C. 随机", "D. 不存在"], "B", "SYN 置 1 表示请求建立连接。"),
        ("choice", 2, "TCP 采用三次握手而非两次的主要原因是？", ["A. 防止已失效的连接请求突然到达造成资源错误分配，并同步双方初始序号", "B. 减少报文数量", "C. 实现数据加密", "D. 实现流量控制"], "A", "第三次握手确认双方收发能力与序号同步。"),
        ("choice", 2, "服务端收到第三次握手的 ACK 后进入的状态是？", ["A. LISTEN", "B. SYN_RCVD", "C. ESTABLISHED", "D. CLOSED"], "C", "连接建立成功，进入 ESTABLISHED。"),
        ("judge", 1, "三次握手过程中双方交换了各自的初始序号。", [], "正确", "SYN 报文携带初始序号 ISN。"),
        ("judge", 2, "两次握手足以可靠地建立 TCP 连接。", [], "错误", "两次握手无法确认客户端的接收能力并防止旧请求。"),
        ("judge", 3, "第三次握手报文可以携带应用数据。", [], "正确", "客户端第三次 ACK 可携带数据。"),
        ("blank", 1, "三次握手的第一个报文是____报文。", [], "SYN", "客户端先发送 SYN。"),
        ("blank", 3, "SYN 洪水攻击利用了服务端在握手过程中处于____状态占用资源。", [], "半连接", "服务端为未完成的握手维护半连接队列。"),
        ("blank", 1, "握手完成后，连接双方都进入____状态。", [], "ESTABLISHED", "连接建立后进入已建立状态。"),
    ],
    ("计算机网络", "TCP 拥塞控制"): [
        ("choice", 1, "TCP 拥塞控制的机制不包括？", ["A. 慢启动", "B. 拥塞避免", "C. 快重传", "D. 静态路由"], "D", "静态路由与拥塞控制无关。"),
        ("choice", 2, "慢启动阶段，拥塞窗口每经过一个 RTT 的变化是？", ["A. 减半", "B. 加 1 个 MSS", "C. 翻倍", "D. 保持不变"], "C", "慢启动按指数增长，每 RTT 翻倍。"),
        ("choice", 3, "发生超时重传后，ssthresh 被设置为？", ["A. 当前拥塞窗口的一半", "B. 拥塞窗口的 2 倍", "C. 0", "D. 保持不变"], "A", "超时说明拥塞严重，阈值减半并重新慢启动。"),
        ("choice", 2, "接收方连续收到 3 个重复 ACK 会触发？", ["A. 快重传", "B. 重新三次握手", "C. 关闭连接", "D. 重启慢启动"], "A", "3 个重复 ACK 触发快重传进入快恢复。"),
        ("judge", 2, "拥塞避免阶段拥塞窗口按线性方式增长。", [], "正确", "每 RTT 加 1 个 MSS，线性加法增大。"),
        ("judge", 2, "慢启动阶段拥塞窗口的增长是线性的。", [], "错误", "慢启动是指数增长。"),
        ("judge", 2, "快恢复阶段拥塞窗口减半后转为线性增长。", [], "正确", "快恢复不回到 1，减半后线性增长。"),
        ("blank", 1, "拥塞窗口的常用英文缩写是____。", [], "cwnd", "拥塞窗口记作 cwnd。"),
        ("blank", 2, "慢启动的阈值称为____。", [], "ssthresh", "慢启动门限记作 ssthresh。"),
        ("blank", 2, "超时后拥塞窗口被重置为____个 MSS 并重新开始慢启动。", [], "1", "超时后 cwnd=1 重新慢启动。"),
    ],
    ("计算机网络", "DNS"): [
        ("choice", 1, "DNS 系统的主要作用是？", ["A. 把域名解析为 IP 地址", "B. 传输网页文件", "C. 发送电子邮件", "D. 动态分配 IP 地址"], "A", "DNS 提供域名到 IP 的解析服务。"),
        ("choice", 1, "DNS 查询默认使用的传输协议与端口是？", ["A. TCP 80", "B. UDP 53", "C. TCP 25", "D. UDP 67"], "B", "常规查询用 UDP 53，区域传送用 TCP 53。"),
        ("choice", 1, "顶级域名 .cn 属于？", ["A. 通用顶级域名", "B. 国家和地区顶级域名", "C. 反向域名", "D. 根域名"], "B", ".cn 是中国的国家顶级域名。"),
        ("choice", 2, "主机向本地域名服务器发起的查询方式通常是？", ["A. 迭代查询", "B. 递归查询", "C. 广播查询", "D. 组播查询"], "B", "主机→本地服务器用递归查询。"),
        ("judge", 2, "DNS 区域传送使用 TCP 协议。", [], "正确", "大数据量传送需要 TCP 的可靠性。"),
        ("judge", 2, "DNS 只能完成域名到 IP 地址的正向解析。", [], "错误", "DNS 也支持反向解析（PTR 记录）。"),
        ("judge", 1, "本地域名服务器的缓存可以加快域名解析。", [], "正确", "缓存命中可省去递归查询。"),
        ("blank", 1, "DNS 资源记录中，域名对应 IPv4 地址的记录类型是____。", [], "A", "A 记录给出域名对应的 IPv4 地址。"),
        ("blank", 2, "标识邮件服务器优先级的 DNS 记录类型是____。", [], "MX", "MX 记录指向邮件交换服务器。"),
        ("blank", 1, "域名 www.example.com 中，顶级域名是____。", [], "com", "最右侧为顶级域名。"),
    ],
    ("计算机网络", "HTTP"): [
        ("choice", 1, "HTTP 协议默认使用的 TCP 端口是？", ["A. 21", "B. 25", "C. 80", "D. 443"], "C", "HTTP 默认 80，HTTPS 默认 443。"),
        ("choice", 2, "下列 HTTP 方法中不具有幂等性的是？", ["A. GET", "B. PUT", "C. DELETE", "D. POST"], "D", "POST 每次执行可能产生不同结果，不幂等。"),
        ("choice", 2, "HTTP“无状态”的含义是？", ["A. 服务器默认不保存客户端的上下文状态", "B. 不能传输数据", "C. 不建立 TCP 连接", "D. 响应没有头部"], "A", "每个请求相互独立，需 Cookie 等机制维持状态。"),
        ("choice", 1, "HTTP 状态码 404 表示？", ["A. 服务器内部错误", "B. 请求的资源未找到", "C. 重定向", "D. 未授权"], "B", "4xx 为客户端错误，404=Not Found。"),
        ("judge", 1, "HTTPS 是运行在 TLS/SSL 之上的 HTTP。", [], "正确", "HTTPS=HTTP over TLS/SSL。"),
        ("judge", 1, "HTTP/1.1 默认使用持久连接。", [], "正确", "1.1 默认 Connection: keep-alive。"),
        ("judge", 1, "Cookie 是在无状态的 HTTP 上维持会话状态的常用机制。", [], "正确", "Cookie/Session 弥补无状态。"),
        ("blank", 1, "HTTP 报文分为请求报文和____报文。", [], "响应", "请求报文与响应报文两类。"),
        ("blank", 2, "只获取资源头部而不取正文的 HTTP 方法是____。", [], "HEAD", "HEAD 方法只返回响应头。"),
        ("blank", 2, "状态码 301 表示资源____移动（永久重定向）。", [], "永久", "301=永久重定向，302=临时重定向。"),
    ],
}


def ensure_demo_bank(db_path: Path, per_point: int = CLASS_SCOPE_MIN) -> dict:
    """Author objective demo questions for scope points that lack a demo bank."""
    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.learning import Exercise, KnowledgePoint, SystemSubject

    report = {"authored": 0, "points_ready": [], "still_missing": []}
    targets = _scope_targets(db_path)
    with SessionLocal() as db:
        for subject_name, point_name, _class_ids in targets:
            subject = db.query(SystemSubject).filter(SystemSubject.name == subject_name).first()
            point = (
                db.query(KnowledgePoint)
                .filter(KnowledgePoint.subject_id == subject.id, KnowledgePoint.name == point_name)
                .first()
            )
            if point is None:
                report["still_missing"].append(f"{subject_name}/{point_name}: 知识点行不存在")
                continue
            have = (
                db.query(Exercise)
                .filter(
                    Exercise.knowledge_point_id == point.id,
                    Exercise.assistant_operation_key.like(DEMO_KEY_GLOB),
                )
                .count()
            )
            if have >= per_point:
                report["points_ready"].append({"point": point_name, "questions": have, "authored": 0})
                continue
            source = BANK.get((subject_name, point_name)) or []
            if not source:
                report["still_missing"].append(f"{subject_name}/{point_name}: 无已编制的演示题，未伪造")
                continue
            created = 0
            for index, (qtype, difficulty, prompt, options, answer, analysis) in enumerate(source, start=1):
                key = f"{AUTHORED_KEY_PREFIX}{point.id}-{index}"
                if db.query(Exercise).filter(Exercise.assistant_operation_key == key).first():
                    continue
                payload = {
                    "prompt": prompt,
                    "classification_status": "completed",
                    "demo_authored": True,
                }
                if options:
                    payload["options"] = options
                db.add(
                    Exercise(
                        knowledge_point_id=point.id,
                        type=qtype,
                        difficulty=difficulty,
                        content=json.dumps(payload, ensure_ascii=False),
                        answer=answer,
                        analysis=analysis,
                        assistant_operation_key=key,
                    )
                )
                created += 1
            db.commit()
            total = (
                db.query(Exercise)
                .filter(
                    Exercise.knowledge_point_id == point.id,
                    Exercise.assistant_operation_key.like(DEMO_KEY_GLOB),
                )
                .count()
            )
            report["authored"] += created
            report["points_ready"].append({"point": point_name, "questions": total, "authored": created})
    return report


def _scope_targets(db_path: Path) -> list[tuple[str, str, list[int]]]:
    """(subject, point_name, class_ids) for every demo teaching class scope point."""
    import sqlite3

    db = sqlite3.connect(db_path)
    merged: dict[tuple[str, str], list[int]] = {}
    for subject, class_id, raw in db.execute(
        """
        SELECT c.subject, ts.class_id, ts.knowledge_points
        FROM teaching_scopes ts JOIN classrooms c ON c.id = ts.class_id
        WHERE c.name LIKE '[DEMO]%' AND c.course_id IS NOT NULL AND c.name NOT LIKE '%行政班%'
        """
    ):
        try:
            points = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            points = []
        for name in points or []:
            if isinstance(name, str) and name.strip():
                merged.setdefault((subject, name.strip()), []).append(class_id)
    db.close()
    return [(subject, point, ids) for (subject, point), ids in sorted(merged.items())]


# --------------------------------------------------------------------------- #
# Phase B · real answers over HTTP (server-side grading)
# --------------------------------------------------------------------------- #
def load_demo_bank(db_path: Path) -> dict[str, list[dict]]:
    """point name → demo questions (cloned + authored), read-only."""
    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.learning import Exercise, KnowledgePoint

    with SessionLocal() as db:
        rows = (
            db.query(Exercise, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == Exercise.knowledge_point_id)
            .filter(Exercise.assistant_operation_key.like(DEMO_KEY_GLOB))
            .order_by(Exercise.id)
            .all()
        )
        bank: dict[str, list[dict]] = {}
        for exercise, point in rows:
            try:
                payload = json.loads(exercise.content or "{}")
            except (TypeError, ValueError):
                payload = {}
            options = [str(item) for item in (payload.get("options") or [])]
            bank.setdefault(point.name, []).append(
                {
                    "id": exercise.id,
                    "knowledge_point": point.name,
                    "type": exercise.type,
                    "difficulty": int(exercise.difficulty or 1),
                    "answer": str(exercise.answer or ""),
                    "options": options,
                }
            )
    return bank


def login(username: str) -> dict:
    response = HTTP.post(
        f"{USER_API_BASE}/users/login",
        json={"username": username, "password": DEFAULT_PASSWORD},
        timeout=60,
    )
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    token = payload.get("access_token") or payload.get("token") or ""
    return {"token": token, "user_id": int(payload.get("user_id") or 0)}


def supplement_answers(db_path: Path, per_point: int = DEFAULT_QUESTIONS_PER_STUDENT) -> dict:
    """Each demo student answers per_point distinct demo questions per scope point."""
    import sqlite3

    configure_database(db_path)
    persona_by_username = {f"demo_{spec.key}": spec.persona for spec in STUDENTS}

    bank = load_demo_bank(db_path)
    targets = _scope_targets(db_path)

    # read-only snapshot of already-answered questions
    answered: dict[int, set[int]] = {}
    conn = sqlite3.connect(db_path)
    for user_id, exercise_id in conn.execute("SELECT user_id, exercise_id FROM answer_records"):
        answered.setdefault(user_id, set()).add(exercise_id)
    conn.close()

    # class → scope points; class members
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    classes: dict[int, dict] = {}
    for row in conn.execute(
        """
        SELECT c.id, c.name, c.subject, c.teacher_user_id, u.username teacher_username
        FROM classrooms c LEFT JOIN users u ON u.id = c.teacher_user_id
        WHERE c.name LIKE '[DEMO]%' AND c.course_id IS NOT NULL AND c.name NOT LIKE '%行政班%'
        """
    ):
        classes[row["id"]] = {
            "name": row["name"],
            "subject": row["subject"],
            "teacher": row["teacher_username"],
            "points": [],
            "members": [],
        }
    scope_rows = list(
        conn.execute(
            "SELECT class_id, knowledge_points FROM teaching_scopes WHERE class_id IN (%s)"
            % ",".join("?" * len(classes)),
            list(classes.keys()),
        )
    )
    for class_id, raw in scope_rows:
        try:
            points = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            points = []
        if isinstance(classes.get(class_id), dict):
            for name in points or []:
                if isinstance(name, str) and name.strip() and name.strip() not in classes[class_id]["points"]:
                    classes[class_id]["points"].append(name.strip())
    for class_id, user_id in conn.execute(
        "SELECT class_id, student_user_id FROM class_enrollments WHERE class_id IN (%s)"
        % ",".join("?" * len(classes)),
        list(classes.keys()),
    ):
        if isinstance(classes.get(class_id), dict):
            classes[class_id]["members"].append(int(user_id))
    usernames = {
        row[0]: row[1] for row in conn.execute("SELECT id, username FROM users WHERE username LIKE 'demo_s%'")
    }
    conn.close()

    tokens: dict[str, dict] = {}
    outcomes = {"classes": [], "students": []}

    # ---- build one unit per (class, student); units are disjoint ------------
    units: list[dict] = []
    for class_id, room in sorted(classes.items()):
        room["usable_points"] = [name for name in room["points"] if bank.get(name)]
        for user_id in sorted(room["members"]):
            units.append(
                {
                    "class_id": class_id,
                    "room": room,
                    "user_id": user_id,
                    "username": usernames.get(user_id, f"id-{user_id}"),
                }
            )

    def _answer_unit(unit: dict) -> dict:
        username = unit["username"]
        user_id = unit["user_id"]
        room = unit["room"]
        auth = tokens.get(username)
        if auth is None:
            auth = login(username)
            tokens[username] = auth
        if not auth["token"]:
            return {"username": username, "class": room["name"], "error": "login failed"}
        persona = persona_by_username.get(username, "normal")
        accuracy = PERSONA_ACCURACY.get(persona, 0.7)
        records: list[dict] = []
        for point_name in room["usable_points"]:
            fresh = [q for q in bank[point_name] if q["id"] not in answered.get(user_id, set())]
            fresh = fresh[:per_point]
            for question in fresh:
                correct = _ratio(username, question["id"], "supp-v1") < accuracy
                records.append(
                    {
                        "user_id": str(user_id),
                        "exercise_id": str(question["id"]),
                        "user_answer": _answer_payload(question, correct),
                        "time_spent": round(25 + _ratio(username, question["id"], "t2") * 140, 1),
                        "exercise_type": "fill" if question["type"] in {"blank", "fill"} else question["type"],
                        "difficulty": "intermediate",
                        "client_request_id": f"supp-{username}-{question['id']}",
                        "knowledge_point_ids": [question["knowledge_point"]],
                    }
                )
        if not records:
            return {"username": username, "persona": persona, "class": room["name"],
                    "submitted": 0, "graded": 0, "correct": 0, "http_status": 200}
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        response = None
        body = {}
        for attempt in (1, 2, 3):
            try:
                response = session.post(
                    f"{EVAL_API}/evaluation/batch_submit",
                    json={"records": records},
                    headers={"Authorization": f"Bearer {auth['token']}"},
                    timeout=REQUEST_TIMEOUT,
                )
                body = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                if response.status_code == 200:
                    break
            except requests.RequestException as exc:
                print(f"[warn] {username} {room['name']} attempt {attempt} failed: {exc}")
                time.sleep(3)
        finally_closed = session.close()
        del finally_closed
        payload = body.get("data", body) if isinstance(body, dict) else {}
        results = payload.get("results") if isinstance(payload, dict) else payload
        graded_flags = [bool(item.get("is_correct")) for item in (results or []) if isinstance(item, dict)]
        if response is None:
            print(f"[FAIL] {username} {room['name']} 提交三次均失败，跳过")
        return {
            "username": username,
            "persona": persona,
            "class": room["name"],
            "submitted": len(records),
            "graded": len(graded_flags),
            "correct": sum(1 for flag in graded_flags if flag),
            "http_status": response.status_code if response is not None else 0,
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = args_workers = 4
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_answer_unit, unit): unit for unit in units}
        for future in as_completed(futures):
            unit = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:  # noqa: BLE001
                outcome = {
                    "username": unit["username"], "class": unit["room"]["name"],
                    "error": f"unhandled: {exc}",
                }
            outcomes["students"].append(outcome)
            print(f"[submit] {outcome.get('username')} · {outcome.get('class')} "
                  f"submitted={outcome.get('submitted')} graded={outcome.get('graded')} "
                  f"correct={outcome.get('correct')} status={outcome.get('http_status', outcome.get('error'))}")

    for class_id, room in sorted(classes.items()):
        rows = [item for item in outcomes["students"] if item.get("class") == room["name"]]
        outcomes["classes"].append(
            {
                "class": room["name"],
                "points": sorted(set(room["usable_points"])),
                "students": sum(1 for item in rows if item.get("http_status") == 200),
                "submitted": sum(int(item.get("submitted") or 0) for item in rows),
            }
        )
    return outcomes


# --------------------------------------------------------------------------- #
# Phase C · verification: sufficiency + API linkage + persona gradient
# --------------------------------------------------------------------------- #
def verify(db_path: Path) -> dict:
    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.learning import (
        ClassEnrollment,
        Classroom,
        KnowledgePoint,
        SystemSubject,
        TeachingScope,
        User,
    )
    from common.learning_evidence import load_evidence, summarize

    checks: list[dict] = []
    ok_all = True
    with SessionLocal() as db:
        rooms = (
            db.query(Classroom)
            .filter(Classroom.name.like("[DEMO]%"), Classroom.course_id.isnot(None))
            .all()
        )
        for room in rooms:
            subject = db.query(SystemSubject).filter(SystemSubject.name == room.subject).first()
            if subject is None:
                continue
            scopes = db.query(TeachingScope).filter(TeachingScope.class_id == room.id).all()
            points = []
            for scope in scopes:
                for name in scope.knowledge_points or []:
                    if name not in points:
                        points.append(name)
            if not points:
                # 没有教学范围就没有证据链可言，不属于"证据充足"的校验对象。
                continue
            member_rows = (
                db.query(User)
                .join(ClassEnrollment, ClassEnrollment.student_user_id == User.id)
                .filter(ClassEnrollment.class_id == room.id)
                .all()
            )
            persona_by_username = {f"demo_{spec.key}": spec.persona for spec in STUDENTS}
            class_ok = True
            point_stats = {}
            for point_name in points:
                point = (
                    db.query(KnowledgePoint)
                    .filter(KnowledgePoint.subject_id == subject.id, KnowledgePoint.name == point_name)
                    .first()
                )
                if point is None:
                    checks.append({"class": room.name, "check": f"知识点行存在: {point_name}", "ok": False, "detail": "missing"})
                    class_ok = ok_all = False
                    continue
                stats_per_student = []
                for member in member_rows:
                    records = load_evidence(db, member.id, point=point)
                    stats = summarize(records)
                    sufficient = stats["status"] == "sufficient" and stats["mastery_score"] is not None
                    stats_per_student.append(
                        {
                            "username": member.username,
                            "persona": persona_by_username.get(member.username, "normal"),
                            "sample_size": stats["sample_size"],
                            "status": stats["status"],
                            "mastery": stats["mastery_score"],
                            "correct_rate": stats["correct_rate"],
                        }
                    )
                    if not sufficient:
                        class_ok = ok_all = False
                point_stats[point_name] = stats_per_student
                masteries = [item["mastery"] for item in stats_per_student if item["mastery"] is not None]
                checks.append(
                    {
                        "class": room.name,
                        "check": f"{point_name}: 每生证据 sufficient 且掌握度非空",
                        "ok": bool(stats_per_student) and all(
                            item["status"] == "sufficient" and item["mastery"] is not None
                            for item in stats_per_student
                        ),
                        "detail": f"samples={[item['sample_size'] for item in stats_per_student]}",
                    }
                )
                checks.append(
                    {
                        "class": room.name,
                        "check": f"{point_name}: 掌握度存在差异 (distinct>=2)",
                        "ok": len(set(masteries)) >= 2,
                        "detail": f"mastery={sorted(set(masteries))}",
                    }
                )
            # persona gradient: excellent > struggling on class average
            def avg_mastery(persona: str) -> float | None:
                values = [
                    item["mastery"]
                    for stats in point_stats.values()
                    for item in stats
                    if item["persona"] == persona and item["mastery"] is not None
                ]
                return round(sum(values) / len(values), 1) if values else None

            excellent, struggling = avg_mastery("excellent"), avg_mastery("struggling")
            if excellent is not None and struggling is not None:
                checks.append(
                    {
                        "class": room.name,
                        "check": "画像梯度: excellent 平均掌握度 > struggling",
                        "ok": excellent > struggling,
                        "detail": f"excellent={excellent} struggling={struggling}",
                    }
                )
            else:
                checks.append(
                    {
                        "class": room.name,
                        "check": "画像梯度: excellent 与 struggling 均有数据",
                        "ok": False,
                        "detail": f"excellent={excellent} struggling={struggling}",
                    }
                )
                class_ok = ok_all = False
            ok_all = ok_all and class_ok

        # API-level linkage per class (only classes that own an evidence chain)
        api_results = []
        teacher_tokens: dict[str, str] = {}
        scoped_room_ids = set()
        with SessionLocal() as db2:
            for room_id, in db2.query(TeachingScope.class_id).distinct():
                scoped_room_ids.add(room_id)
        for room in rooms:
            if room.id not in scoped_room_ids:
                continue
            owner = db.query(User).filter(User.id == room.teacher_user_id).first()
            if owner is None:
                continue
            token = teacher_tokens.get(owner.username)
            if not token:
                response = HTTP.post(
                    f"{USER_API_BASE}/users/login",
                    json={"username": owner.username, "password": DEFAULT_PASSWORD},
                    timeout=60,
                )
                payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                token = payload.get("access_token") or ""
                teacher_tokens[owner.username] = token
            if not token:
                api_results.append({"class": room.name, "ok": False, "detail": "teacher login failed"})
                ok_all = False
                continue
            headers = {"Authorization": f"Bearer {token}"}
            insights_response = HTTP.get(
                f"{TEACHER_API}/teacher/classes/{room.id}/insights", headers=headers, timeout=120
            )
            insights = (insights_response.json() or {}).get("data") if insights_response.headers.get("content-type", "").startswith("application/json") else None
            insights = insights if isinstance(insights, list) else []
            masteries = [item.get("mastery") for item in insights if isinstance(item.get("mastery"), int)]
            mistakes = [item.get("mistake_count") for item in insights if isinstance(item.get("mistake_count"), int)]
            api_ok = (
                insights_response.status_code == 200
                and bool(masteries)
                and all(1 <= m <= 100 for m in masteries)
                and len(set(masteries)) >= 2
                and any((m or 0) > 0 for m in mistakes)
            )
            analytics_response = HTTP.get(
                f"{TEACHER_API}/teacher/classes/{room.id}/teaching-analytics", headers=headers, timeout=120
            )
            analytics = (analytics_response.json() or {}).get("data") if analytics_response.headers.get("content-type", "").startswith("application/json") else {}
            analytics = analytics if isinstance(analytics, dict) else {}
            api_ok = api_ok and int(analytics.get("total_answers") or 0) > 0 and bool(analytics.get("weak_knowledge_points"))
            api_results.append(
                {
                    "class": room.name,
                    "check": "教师端 insights / teaching-analytics 联动正常",
                    "ok": api_ok,
                    "detail": (
                        f"mastery={sorted(set(masteries))} mistakes_max={max((m or 0) for m in mistakes) if mistakes else 0} "
                        f"total_answers={analytics.get('total_answers')} weak={[item.get('knowledge_point') if isinstance(item, dict) else item for item in (analytics.get('weak_knowledge_points') or [])]}"
                    ),
                }
            )
            if not api_ok:
                ok_all = False
        checks.extend(api_results)

    return {"all_pass": ok_all, "checks": checks}


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--skip-bank", action="store_true", help="跳过造题，只补作答与校验")
    parser.add_argument("--verify-only", action="store_true", help="只做证据充足性校验")
    parser.add_argument("--per-point", type=int, default=DEFAULT_QUESTIONS_PER_STUDENT)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "artifacts" / "demo-teaching" / f"evidence-supplement-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {"generated_at": datetime.now(TZ).isoformat(), "database": str(db_path)}

    if not args.verify_only and not args.skip_bank:
        result["bank"] = ensure_demo_bank(db_path)
        print(f"[bank] authored={result['bank']['authored']} missing={result['bank']['still_missing']}")
    if not args.verify_only:
        result["answers"] = supplement_answers(db_path, args.per_point)
        print(
            f"[answers] classes={len(result['answers']['classes'])} "
            f"students={len(result['answers']['students'])}"
        )
    result["verify"] = verify(db_path)
    print(f"[verify] all_pass={result['verify']['all_pass']}")
    for item in result["verify"]["checks"]:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['class']} · {item.get('check', item.get('ok', ''))} ({item['detail']})")

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 演示账号证据补充报告",
        "",
        f"生成时间：`{result['generated_at']}`，运行库：`{db_path}`",
        "",
        "## 结论",
        "",
        f"- 证据充足性总体校验：**{'全部通过' if result['verify']['all_pass'] else '存在未通过项'}**",
        "",
        "## 校验明细",
        "",
        "| 班级 | 校验 | 结果 | 明细 |",
        "| --- | --- | --- | --- |",
    ]
    for item in result["verify"]["checks"]:
        lines.append(
            f"| {item['class']} | {item['check']} | {'PASS' if item['ok'] else 'FAIL'} | {item['detail']} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"evidence: {out_dir}")
    return 0 if result["verify"]["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
