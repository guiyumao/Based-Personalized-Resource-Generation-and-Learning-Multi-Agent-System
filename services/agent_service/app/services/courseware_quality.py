"""Executable teaching contracts, independent of model self-assessment."""
import re

VERSION = "teaching-v2"


def teaching_modules(topic, subject=""):
    text = f"{subject} {topic}".lower()
    domain = "algorithm" if any(x in text for x in ("排序", "算法", "sorting")) else "network" if any(x in text for x in ("tcp", "网络", "协议")) else "structure" if any(x in text for x in ("链表", "数据结构", "树", "list")) else "math" if any(x in text for x in ("数学", "公式", "方程", "推导", "积分", "导数", "概率", "math")) else "general"
    principles = {
        "algorithm": "算法思想、完整伪代码、循环边界、不变量、最好/平均/最坏时间及空间复杂度、稳定性、适用条件",
        "network": "所属体系结构、协议作用、关键报文字段、通信机制、交互过程、边界条件及典型网络场景",
        "structure": "逻辑结构、存储结构、节点和指针、完整操作步骤/代码、边界及时间空间复杂度",
        "general": "核心机制、条件、完整方法、步骤依据、适用场景与边界；只添加本主题需要的代码或公式",
        "math": "定义、符号、适用条件、逐步公式推导及每一步的依据，解释边界与反例",
    }[domain]
    return domain, [
        ("intro", "课程导入与学习目标", "学习背景、实际应用、与已有知识联系、至少3个可检验目标、前置知识、预计学习时间"),
        ("concepts", "核心概念", "先通俗直觉再严谨定义、术语、概念关系、适用条件与误解"),
        ("principles", "核心原理", principles),
        ("visual", "步骤与状态对照", "不生成流程图或Mermaid flowchart/graph；使用编号文字步骤和规范Markdown表格解释过程，列出输入、中间状态与结果，配完整文字说明"),
        ("case", "完整案例分析", "明确问题背景、输入/已知条件、选择方法原因；至少3个带中间状态的步骤，分别以### 步骤1/步骤2/步骤3为标题，最终结果、核验、错误做法及案例总结"),
        ("compare", "相关知识与适用条件对比", "只比较相关概念，用表格说明条件、区别、代价；不适合对比时解释本主题的边界和适用条件"),
        ("mistakes", "常见错误与易错考点", "逐项说明误解、原因、正确理解、快速判断及特殊情况；没有可信错题时明确标注通用易错点"),
        ("practice", "知识巩固练习", "至少3道本主题题目，覆盖基础理解、过程分析和综合应用；每题用### 题目N，答案分别用### 答案与解析N，给标准答案及具体解题步骤"),
        ("summary", "总结与知识拓展", "核心知识结构、关键规律、前后章节联系、基础必学/选学拓展分开，不编造引用或外链"),
    ]


def check_module(key, body):
    issues = []
    if len(re.sub(r"\s", "", body)) < (300 if key in {"principles", "case", "practice"} else 180):
        issues.append("章节缺少实质讲解")
    if len(re.findall(r"^```", body, re.M)) % 2:
        issues.append("代码围栏未闭合")
    if len(re.findall(r"^\s*\$\$\s*$", body, re.M)) % 2:
        issues.append("公式定界符未闭合")
    if key == "case" and max(len(re.findall(r"(?:步骤|第[一二三四五六七八九\d]+[步轮趟]|^\s*(?:#{1,6}\s*)?\d+[.、])", body, re.M)), len(re.findall(r"^\|[^\n]*\d[^\n]*\|$", body, re.M))) < 3:
        issues.append("案例缺少至少三个中间步骤")
    if key == "practice" and (len(re.findall(r"^###\s*题目", body, re.M)) < 3 or len(re.findall(r"^###\s*答案与解析", body, re.M)) < 3):
        issues.append("至少三道题应分别提供标准答案和解析")
    if key == "visual" and len(re.findall(r"^\|.*\|$", body, re.M)) < 3:
        issues.append("缺少规范步骤或状态对照表格")
    if re.search(r"```mermaid[^\n]*\n(?:\s|%%[^\n]*\n)*(?:flowchart|graph)\b", body, re.I):
        issues.append("课件不需要流程图，请改为文字步骤与表格")
    if key == "practice":
        questions = re.findall(r"^###\s*题目\s*([0-9一二三四五六七八九]+)", body, re.M)
        answers = re.findall(r"^###\s*答案与解析\s*([0-9一二三四五六七八九]+)", body, re.M)
        if len(questions) < 3 or len(set(questions)) != len(questions) or set(questions) != set(answers):
            issues.append("题号和答案解析必须一一对应")
    return issues


def report(chapters, sources):
    issues = {c["key"]: check_module(c["key"], c["body"]) for c in chapters}
    return {"version": VERSION, "status": "passed" if not any(issues.values()) and len(chapters) == 9 else "needs_revision",
            "chapter_checks": issues, "chapter_count": len(chapters),
            "source_status": "retrieved_references" if sources else "model_generated_unverified",
            "semantic_accuracy": "requires_subject_review", "checks": "structure_depth_steps_answers_and_delimiters"}
