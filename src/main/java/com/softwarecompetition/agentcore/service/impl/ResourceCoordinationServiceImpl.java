package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.*;
import com.softwarecompetition.agentcore.entity.Resource;
import com.softwarecompetition.agentcore.entity.ResourceGenerationRecord;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.mapper.ResourceGenerationRecordMapper;
import com.softwarecompetition.agentcore.mapper.ResourceMapper;
import com.softwarecompetition.agentcore.messaging.ResourceGenerationMessage;
import com.softwarecompetition.agentcore.messaging.ResourceGenerationProducer;
import com.softwarecompetition.agentcore.service.ResourceCoordinationService;
import com.softwarecompetition.agentcore.service.ResourceGenerationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class ResourceCoordinationServiceImpl implements ResourceCoordinationService {

    private static final Logger log = LoggerFactory.getLogger(ResourceCoordinationServiceImpl.class);

    private final ResourceGenerationService generationService;
    private final DeepSeekClient deepSeekClient;
    private final ResourceGenerationRecordMapper recordMapper;
    private final ResourceMapper resourceMapper;
    private final ResourceGenerationProducer producer;
    private final com.softwarecompetition.agentcore.service.UserProfileService userProfileService;
    private final ObjectMapper objectMapper;

    public ResourceCoordinationServiceImpl(ResourceGenerationService generationService,
                                           DeepSeekClient deepSeekClient,
                                           ResourceGenerationRecordMapper recordMapper,
                                           ResourceMapper resourceMapper,
                                           ResourceGenerationProducer producer,
                                           com.softwarecompetition.agentcore.service.UserProfileService userProfileService) {
        this.generationService = generationService;
        this.deepSeekClient = deepSeekClient;
        this.recordMapper = recordMapper;
        this.resourceMapper = resourceMapper;
        this.producer = producer;
        this.userProfileService = userProfileService;
        this.objectMapper = new ObjectMapper();
    }

    private static final String ANALYZE_PROMPT =
        "你是资源生成协调智能体。你需要深度分析用户的学习需求，输出结构化的生成方案。" +
        "支持5种资源类型：lecture(讲解文档), mindmap(思维导图), exercise(练习题), " +
        "extended_reading(拓展阅读), code_example(代码案例)。\n\n" +
        "分析规则：\n" +
        "1. 从用户原文中精确提取主题和知识点，不要替换为用户没提到的内容\n" +
        "2. 如果用户指定了类型（文档/导图/题目等），直接用；否则根据需求性质推断\n" +
        "3. 根据知识点和字数要求规划3-6个章节的大纲\n" +
        "4. 如果用户提到字数/篇幅要求，如实记录；未提到则按资源类型给合理默认值\n" +
        "5. 根据用户画像（知识基础/易错点/学习节奏）生成个性化提示\n\n" +
        "只返回JSON（不要markdown包裹）:\n" +
        "{\n" +
        "  \"resourceType\": \"lecture\",\n" +
        "  \"knowledgePoint\": \"用户原文中的主题\",\n" +
        "  \"titleSuggestion\": \"建议标题\",\n" +
        "  \"suggestedOutline\": [\"章节1\", \"章节2\", \"章节3\", ...],\n" +
        "  \"wordCount\": 3000,\n" +
        "  \"difficulty\": \"medium\",\n" +
        "  \"personalizationHints\": \"基于画像的针对性教学建议\",\n" +
        "  \"style\": \"interactive\"\n" +
        "}";

    @Override
    public ResourceGenerateResponse generate(Long userId, ResourceGenerateRequest request) {
        // 创建生成记录
        ResourceGenerationRecord record = new ResourceGenerationRecord();
        record.setUserId(userId);
        record.setRequestText(request.getRequestText());
        record.setResourceType(request.getResourceType());
        record.setKnowledgePoint(request.getKnowledgePoint());
        record.setStatus("queued");
        recordMapper.insert(record);

        // 发送到消息队列异步处理
        ResourceGenerationMessage message = new ResourceGenerationMessage(
                record.getId(), userId, request.getRequestText(),
                request.getResourceType(), request.getKnowledgePoint());
        producer.send(message);

        log.info("资源生成任务已入队: taskId={}, userId={}", record.getId(), userId);

        ResourceGenerateResponse response = new ResourceGenerateResponse();
        response.setResourceId(record.getId());
        response.setResourceType(request.getResourceType());
        response.setStatus("queued");
        response.setMessage("资源生成任务已提交，预计需要5-15秒");
        return response;
    }

    @Override
    public void executeGeneration(Long taskId, Long userId, ResourceGenerateRequest request) {
        ResourceGenerationRecord record = recordMapper.selectById(taskId);
        if (record == null) {
            log.error("任务记录不存在: taskId={}", taskId);
            return;
        }

        record.setStatus("processing");
        recordMapper.updateById(record);

        try {
            // 无论用户是否指定resourceType，都走深度分析生成完整的GenerationPlan
            GenerationPlan plan = request.getResourceType() != null
                ? buildPlanFromRequest(request)
                : analyzeAndBuildPlan(userId, request);

            Resource resource = generationService.generateResource(userId, plan, request.getRequestText());

            record.setResourceId(resource.getId());
            record.setResourceType(plan.getResourceType());
            record.setKnowledgePoint(plan.getKnowledgePoint());
            record.setStatus("completed");
            record.setCompletedAt(LocalDateTime.now());
            recordMapper.updateById(record);

            log.info("资源生成完成: taskId={}, resourceId={}", taskId, resource.getId());

        } catch (Exception e) {
            log.error("资源生成失败: taskId={}", taskId, e);
            record.setStatus("failed");
            record.setErrorMessage(e.getMessage());
            recordMapper.updateById(record);
        }
    }

    /**
     * 调用LLM深度分析用户需求，生成完整的GenerationPlan。
     * 包含知识点提取、章节大纲、字数、难度、个性化提示。
     */
    private GenerationPlan analyzeAndBuildPlan(Long userId, ResourceGenerateRequest request) {
        try {
            // 加载用户画像作为分析的上下文
            UserProfile profile = userProfileService.getByUserId(userId);
            String profileHint = "";
            if (profile != null) {
                profileHint = String.format("学生画像：知识基础=%s, 学习风格=%s, 易错点=%s, 学习节奏=%s",
                    profile.getKnowledgeBase() != null ? profile.getKnowledgeBase() : "未知",
                    profile.getCognitiveStyle() != null ? profile.getCognitiveStyle() : "未知",
                    profile.getErrorPreference() != null ? profile.getErrorPreference() : "未知",
                    profile.getLearningSpeed() != null ? profile.getLearningSpeed() : "未知");
            }

            String analysisPrompt = profileHint.isEmpty() ? request.getRequestText()
                : profileHint + "\n\n学生需求：" + request.getRequestText();

            String analysisJson = deepSeekClient.chat(
                List.of(
                    Map.of("role", "system", "content", ANALYZE_PROMPT),
                    Map.of("role", "user", "content", analysisPrompt)
                ), 0.3);

            var parsed = objectMapper.readValue(
                extractJson(analysisJson),
                new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {});

            GenerationPlan plan = new GenerationPlan();
            plan.setResourceType((String) parsed.getOrDefault("resourceType", "lecture"));
            plan.setKnowledgePoint((String) parsed.getOrDefault("knowledgePoint", "通用学习"));
            plan.setTitleSuggestion((String) parsed.getOrDefault("titleSuggestion", null));

            @SuppressWarnings("unchecked")
            List<String> outline = (List<String>) parsed.get("suggestedOutline");
            plan.setSuggestedOutline(outline);

            Object wc = parsed.get("wordCount");
            plan.setWordCount(wc instanceof Number ? ((Number) wc).intValue() : 3000);

            plan.setDifficulty((String) parsed.getOrDefault("difficulty", "medium"));
            plan.setPersonalizationHints((String) parsed.getOrDefault("personalizationHints", ""));
            plan.setStyle((String) parsed.getOrDefault("style", "interactive"));

            log.info("需求分析完成: type={}, kp={}, outlineSize={}, words={}",
                plan.getResourceType(), plan.getKnowledgePoint(),
                outline != null ? outline.size() : 0, plan.getWordCount());

            return plan;

        } catch (Exception e) {
            log.warn("深度分析失败，使用基础计划", e);
            return buildPlanFromRequest(request);
        }
    }

    private GenerationPlan buildPlanFromRequest(ResourceGenerateRequest request) {
        GenerationPlan plan = new GenerationPlan();
        plan.setResourceType(request.getResourceType() != null ? request.getResourceType() : "lecture");
        plan.setKnowledgePoint(request.getKnowledgePoint() != null ? request.getKnowledgePoint() : "通用学习");
        plan.setTitleSuggestion(request.getKnowledgePoint() + "学习资料");
        plan.setWordCount(3000);
        plan.setDifficulty("medium");
        return plan;
    }

    @Override
    public ResourceTaskStatusResponse getTaskStatus(Long taskId) {
        ResourceGenerationRecord record = recordMapper.selectById(taskId);
        ResourceTaskStatusResponse response = new ResourceTaskStatusResponse();

        if (record == null) {
            response.setTaskId(taskId);
            response.setStatus("not_found");
            response.setMessage("任务不存在");
            return response;
        }

        response.setTaskId(taskId);
        response.setStatus(record.getStatus());
        response.setResourceId(record.getResourceId());
        response.setMessage(switch (record.getStatus()) {
            case "queued" -> "排队中，等待处理...";
            case "processing" -> "正在生成资源...";
            case "completed" -> "生成完成";
            case "failed" -> "生成失败: " + (record.getErrorMessage() != null ? record.getErrorMessage() : "未知错误");
            default -> record.getStatus();
        });
        return response;
    }

    @Override
    public List<ResourceDto> getHistory(Long userId, int page, int size) {
        LambdaQueryWrapper<Resource> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Resource::getUserId, userId)
                .orderByDesc(Resource::getCreatedAt);
        Page<Resource> result = resourceMapper.selectPage(new Page<>(page, size), wrapper);
        List<ResourceDto> dtos = new ArrayList<>();
        for (Resource r : result.getRecords()) {
            dtos.add(toDto(r));
        }
        return dtos;
    }

    @Override
    @Cacheable(value = "resource", key = "#resourceId", unless = "#result == null")
    public ResourceDto getResource(Long resourceId) {
        Resource r = resourceMapper.selectById(resourceId);
        return r != null ? toDto(r) : null;
    }

    private ResourceDto toDto(Resource r) {
        ResourceDto dto = new ResourceDto();
        dto.setId(r.getId());
        dto.setResourceType(r.getResourceType());
        dto.setTitle(r.getTitle());
        dto.setContent(r.getContent());
        dto.setFormat(r.getFormat());
        dto.setKnowledgePoint(r.getKnowledgePoint());
        dto.setDifficultyLevel(r.getDifficultyLevel());
        dto.setEstimatedTimeMinutes(r.getEstimatedTimeMinutes());
        dto.setStatus(r.getStatus());
        dto.setCreatedAt(r.getCreatedAt());
        return dto;
    }

    private String extractJson(String raw) {
        String trimmed = raw.trim();
        if (trimmed.startsWith("```")) {
            int start = trimmed.indexOf("\n");
            int end = trimmed.lastIndexOf("```");
            if (start >= 0 && end > start) trimmed = trimmed.substring(start, end).trim();
        }
        int firstBrace = trimmed.indexOf('{');
        int lastBrace = trimmed.lastIndexOf('}');
        if (firstBrace >= 0 && lastBrace > firstBrace)
            return trimmed.substring(firstBrace, lastBrace + 1);
        return trimmed;
    }
}
