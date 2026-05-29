package com.education.agentservice.service;

import com.education.agentservice.dto.CoordinationRequest;
import com.education.agentservice.dto.CoordinationResponse;
import com.education.agentservice.dto.ExerciseGenerationRequest;
import com.education.agentservice.dto.GraphQueryRequest;
import com.education.agentservice.dto.LearningPathRequest;
import com.education.agentservice.dto.ResourceGenerationRequest;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class AgentFacadeService {

    public CoordinationResponse coordinate(CoordinationRequest request) {
        return new CoordinationResponse(
            "success",
            List.of("learner_profiling_agent", "path_planning_agent", "resource_generation_agent"),
            "根据当前意图识别到用户需要学习路径、课件和课后自测。",
            Map.of(
                "path_planning_agent", Map.of("message", "已规划阶段任务。"),
                "resource_generation_agent", Map.of("message", "已准备课件与练习生成。")
            )
        );
    }

    public Map<String, Object> generateResource(ResourceGenerationRequest request) {
        String content = """
            # %s 学习课件

            ## 本节你会学到什么
            - 理解 %s 的核心作用
            - 能区分 for 和 while 的适用场景
            - 能识别常见错误并完成课后自测

            ## 常见错误
            - 忘记更新 while 循环的条件变量，导致死循环。
            - 把 range(5) 误解成从 1 到 5，实际是 0 到 4。
            - 循环体缩进错误，导致本该重复执行的语句跑到循环外。

            ## 学完后自测
            - 能否解释 for 和 while 的使用场景差异？
            - 能否写出一个遍历列表并带条件判断的循环？
            - 能否判断一个 while 循环为什么会死循环？
            - 能否用循环解决一个重复输出或统计的问题？
            """.formatted(request.knowledge_point(), request.knowledge_point());

        return Map.of(
            "user_id", request.user_id(),
            "knowledge_point", request.knowledge_point(),
            "resource_type", request.resource_type(),
            "resource_style", request.resource_style(),
            "references", List.of(Map.of("id", "kb-1", "content", "来自知识库的示例内容", "metadata", Map.of("source", "java-fallback"))),
            "content", content
        );
    }

    public Map<String, Object> generateExercises(ExerciseGenerationRequest request) {
        String knowledgePoint = request.knowledge_point();
        return Map.of(
            "user_id", request.user_id(),
            "knowledge_point", knowledgePoint,
            "summary", "已根据当前课件内容生成 5 道课后自测题。",
            "exercises", List.of(
                Map.of(
                    "exercise_id", 1,
                    "knowledge_point", knowledgePoint,
                    "question_type", "choice",
                    "difficulty", "foundation",
                    "prompt", "关于 for 和 while 的使用场景差异，哪项说法最准确？",
                    "options", List.of(
                        "A. while 一定比 for 更适合遍历固定次数任务",
                        "B. for 更适合遍历已知序列，while 更适合依赖条件持续执行",
                        "C. for 和 while 不能和条件判断配合",
                        "D. 只要用了 range 就不能写 if 判断"
                    ),
                    "answer", "B",
                    "analysis", "这道题检查你是否真正理解了两类循环的使用场景。"
                ),
                Map.of(
                    "exercise_id", 2,
                    "knowledge_point", knowledgePoint,
                    "question_type", "blank",
                    "difficulty", "foundation",
                    "prompt", "如果 while 循环中忘记更新控制变量，最可能导致 ______。",
                    "options", List.of(),
                    "answer", "死循环",
                    "analysis", "这题对应课件中的常见错误，重点检查循环退出条件。"
                ),
                Map.of(
                    "exercise_id", 3,
                    "knowledge_point", knowledgePoint,
                    "question_type", "judge",
                    "difficulty", "foundation",
                    "prompt", "判断正误：range(5) 会依次得到 1, 2, 3, 4, 5。",
                    "options", List.of(),
                    "answer", "错误",
                    "analysis", "range(5) 实际上得到的是 0 到 4。"
                ),
                Map.of(
                    "exercise_id", 4,
                    "knowledge_point", knowledgePoint,
                    "question_type", "short_answer",
                    "difficulty", "intermediate",
                    "prompt", "请说明一个 while 循环为什么会死循环，并说出修改方法。",
                    "options", List.of(),
                    "answer", "答案示例：因为条件变量没有更新，导致退出条件永远不成立；应在循环体中更新控制变量。",
                    "analysis", "这题检查你是否能把错误现象和原因关联起来。"
                ),
                Map.of(
                    "exercise_id", 5,
                    "knowledge_point", knowledgePoint,
                    "question_type", "programming",
                    "difficulty", "advanced",
                    "prompt", "编写一段代码，遍历列表并输出所有偶数。",
                    "options", List.of(),
                    "answer", "nums = [1,2,3,4,5]\\nfor num in nums:\\n    if num % 2 == 0:\\n        print(num)",
                    "analysis", "这题对应课件中的遍历列表并带条件判断的自测点。"
                )
            )
        );
    }

    public Map<String, Object> generatePath(LearningPathRequest request) {
        return Map.of(
            "user_id", request.user_id(),
            "subject", request.subject(),
            "knowledge_point", request.knowledge_point(),
            "overview", "先学课件，再做课后自测，最后复盘错题。",
            "estimated_days", 3,
            "stages", List.of(
                Map.of(
                    "stage_id", "stage-1",
                    "title", "阶段一：理解概念",
                    "description", "先理解核心语法和使用场景。",
                    "tasks", List.of(
                        Map.of(
                            "task_id", "task-1",
                            "title", "学习核心课件",
                            "task_type", "courseware",
                            "knowledge_point", request.knowledge_point(),
                            "objective", "理解定义、语法和常见错误。",
                            "estimated_minutes", 20,
                            "difficulty", "foundation",
                            "completed", false
                        )
                    )
                )
            )
        );
    }

    public Map<String, Object> getDependencies(GraphQueryRequest request) {
        return Map.of(
            "knowledge_point", request.knowledge_point(),
            "dependencies", List.of(
                Map.of("path", List.of("基础语法", "条件判断", request.knowledge_point()))
            )
        );
    }

    public Map<String, Object> getVisualization(GraphQueryRequest request) {
        return Map.of(
            "knowledge_point", request.knowledge_point(),
            "nodes", List.of(
                Map.of("id", "n1", "label", "基础语法", "category", "prerequisite"),
                Map.of("id", "n2", "label", "条件判断", "category", "prerequisite"),
                Map.of("id", "n3", "label", request.knowledge_point(), "category", "current")
            ),
            "edges", List.of(
                Map.of("source", "n1", "target", "n3", "label", "depends_on"),
                Map.of("source", "n2", "target", "n3", "label", "depends_on")
            )
        );
    }
}
