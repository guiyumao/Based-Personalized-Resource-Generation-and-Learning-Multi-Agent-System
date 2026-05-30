package com.softwarecompetition.agentcore.service.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.GenerationPlan;
import com.softwarecompetition.agentcore.entity.Resource;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.mapper.LearningRecordMapper;
import com.softwarecompetition.agentcore.mapper.ResourceMapper;
import com.softwarecompetition.agentcore.mapper.UserProgressMapper;
import com.softwarecompetition.agentcore.service.ResourceGenerationService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
public class ResourceGenerationServiceImpl implements ResourceGenerationService {

    private static final Logger log = LoggerFactory.getLogger(ResourceGenerationServiceImpl.class);

    private final DeepSeekClient deepSeekClient;
    private final UserProfileService userProfileService;
    private final ResourceMapper resourceMapper;
    private final ObjectMapper objectMapper;

    public ResourceGenerationServiceImpl(DeepSeekClient deepSeekClient,
                                         UserProfileService userProfileService,
                                         ResourceMapper resourceMapper) {
        this.deepSeekClient = deepSeekClient;
        this.userProfileService = userProfileService;
        this.resourceMapper = resourceMapper;
        this.objectMapper = new ObjectMapper();
    }

    private static final String PROMPT_LECTURE =
        "你是一个专业的课程讲解文档生成智能体。请根据学生的画像和需求，生成一份结构清晰、内容详实的讲解文档。\n" +
        "输出Markdown格式，包含：标题、概述、核心概念讲解（分多个小节）、实例说明、常见误区、总结。" +
        "严格遵循以下几个约束：\n" +
        "- 按照提供的章节大纲组织内容\n" +
        "- 严格控制输出字数\n" +
        "- 根据学生的掌握度和易错点调整讲解详细程度\n" +
        "- 每个公式或关键概念都要有对应的代码示例或类比说明";

    private static final String PROMPT_MINDMAP =
        "你是一个知识思维导图生成智能体。请根据学生的需求，生成一个层次化的知识点思维导图。\n" +
        "输出Markdown格式，使用多级标题(#, ##, ###)表示层次关系，每层3-6个节点。\n" +
        "遵循以下约束：\n" +
        "- 按照建议的大纲结构组织层级\n" +
        "- 覆盖核心概念、子知识点、关键技术点、常见误区\n" +
        "- 根据学生的掌握度决定分叉深度（掌握度低的深挖基础）；掌握度高的增加扩展分支";

    private static final String PROMPT_EXERCISE =
        "你是一个练习题生成智能体。请根据学生的需求和画像，生成针对性的练习题。\n" +
        "输出Markdown格式，每道题包含：题号、题干、选项（如有）、正确答案、详细解析。" +
        "生成3-5道题。" +
        "严格遵循以下约束：\n" +
        "- 根据学生的易错方向设计题目\n" +
        "- 难度分布：40%基础、40%中级、20%难题\n" +
        "- 每道题的解析要包含：正确选项解释、错误选项排除原因、延展知识点";

    private static final String PROMPT_EXTENDED_READING =
        "你是一个拓展阅读推荐智能体。请根据学生的兴趣方向和知识水平，推荐拓展阅读材料。\n" +
        "输出Markdown格式，包含：推荐理由、每篇阅读材料的核心内容概述、延伸方向、参考文献。\n" +
        "严格遵循以下约束：\n" +
        "- 阅读材料从巩固→拔高→前沿，逐步递进\n" +
        "- 根据学生的兴趣方向匹配领域\n" +
        "- 输出约1000-2000字";

    private static final String PROMPT_CODE_EXAMPLE =
        "你是一个代码案例生成智能体。请根据学生的需求，生成可运行的代码示例。\n" +
        "输出Markdown格式，包含：场景说明、完整代码（用```代码块包裹）、关键代码解析、运行结果预期、扩展练习建议。\n" +
        "严格遵循以下约束：\n" +
        "- 代码必须完整可运行，注释充分\n" +
        "- 从简单示例开始，逐步到复杂实战\n" +
        "- 每个代码块都要有对应的输出结果或预期行为说明";

    @Override
    public Resource generateResource(Long userId, GenerationPlan plan, String userRequest) {
        // 加载完整用户画像上下文
        UserProfile profile = userProfileService.getByUserId(userId);
        String profileContext = buildRichProfileContext(profile);

        // 选择对应的System Prompt
        String systemPrompt = selectPrompt(plan.getResourceType());
        String resourceType = plan.getResourceType() != null ? plan.getResourceType() : "lecture";
        String knowledgePoint = plan.getKnowledgePoint() != null ? plan.getKnowledgePoint() : "通用学习";

        // 构建带完整约束的用户提示
        String userPrompt = buildUserPrompt(plan, userRequest, profileContext);

        List<Map<String, String>> messages = List.of(
            Map.of("role", "system", "content", systemPrompt),
            Map.of("role", "user", "content", userPrompt)
        );

        // 调用大模型生成
        String content = deepSeekClient.chat(messages, 0.5);

        // 保存到数据库
        Resource resource = new Resource();
        resource.setUserId(userId);
        resource.setResourceType(resourceType);
        resource.setTitle(plan.getTitleSuggestion() != null ? plan.getTitleSuggestion()
                : knowledgePoint + resourceTypeName(resourceType));
        resource.setContent(content);
        resource.setFormat("markdown");
        resource.setKnowledgePoint(knowledgePoint);
        resource.setDifficultyLevel(plan.getDifficulty() != null ? plan.getDifficulty() : "medium");
        resource.setEstimatedTimeMinutes(estimateTime(resourceType));
        resource.setStatus("ready");
        resourceMapper.insert(resource);

        log.info("资源生成成功: type={}, id={}, title={}", resourceType, resource.getId(), resource.getTitle());
        return resource;
    }

    private String buildRichProfileContext(UserProfile profile) {
        if (profile == null) return "新学生，画像待构建";
        StringBuilder sb = new StringBuilder();
        sb.append("【学生画像】\n");
        if (profile.getKnowledgeBase() != null)
            sb.append("- 已掌握知识: ").append(profile.getKnowledgeBase()).append("\n");
        if (profile.getCognitiveStyle() != null)
            sb.append("- 偏好学习方式: ").append(profile.getCognitiveStyle()).append("\n");
        if (profile.getErrorPreference() != null)
            sb.append("- 常见易错点: ").append(profile.getErrorPreference()).append("\n");
        if (profile.getLearningSpeed() != null)
            sb.append("- 学习节奏: ").append(profile.getLearningSpeed()).append("\n");
        if (profile.getInterestDirection() != null)
            sb.append("- 兴趣方向: ").append(profile.getInterestDirection()).append("\n");
        if (profile.getGoalOrientation() != null)
            sb.append("- 学习目标: ").append(profile.getGoalOrientation()).append("\n");
        return sb.toString();
    }

    private String buildUserPrompt(GenerationPlan plan, String userRequest, String profileContext) {
        StringBuilder sb = new StringBuilder();
        sb.append(profileContext).append("\n");
        sb.append("【用户原始需求】\n").append(userRequest).append("\n\n");

        if (plan.getSuggestedOutline() != null && !plan.getSuggestedOutline().isEmpty()) {
            sb.append("【章节大纲（严格遵循）】\n");
            for (String item : plan.getSuggestedOutline()) {
                sb.append("- ").append(item).append("\n");
            }
            sb.append("\n");
        }

        if (plan.getWordCount() != null && plan.getWordCount() > 0) {
            sb.append("【字数要求】约").append(plan.getWordCount()).append("字\n\n");
        }

        if (plan.getPersonalizationHints() != null && !plan.getPersonalizationHints().isBlank()) {
            sb.append("【个性化提示】").append(plan.getPersonalizationHints()).append("\n\n");
        }

        sb.append("请严格按照以上约束生成完整的资源内容。");
        return sb.toString();
    }

    private String selectPrompt(String resourceType) {
        return switch (resourceType) {
            case "mindmap" -> PROMPT_MINDMAP;
            case "exercise" -> PROMPT_EXERCISE;
            case "extended_reading" -> PROMPT_EXTENDED_READING;
            case "code_example" -> PROMPT_CODE_EXAMPLE;
            default -> PROMPT_LECTURE;
        };
    }

    private String resourceTypeName(String type) {
        return switch (type) {
            case "lecture" -> "讲解文档";
            case "mindmap" -> "思维导图";
            case "exercise" -> "练习题";
            case "extended_reading" -> "拓展阅读";
            case "code_example" -> "代码案例";
            default -> "学习资源";
        };
    }

    private int estimateTime(String resourceType) {
        return switch (resourceType) {
            case "lecture" -> 30;
            case "mindmap" -> 10;
            case "exercise" -> 30;
            case "extended_reading" -> 15;
            case "code_example" -> 25;
            default -> 20;
        };
    }
}
