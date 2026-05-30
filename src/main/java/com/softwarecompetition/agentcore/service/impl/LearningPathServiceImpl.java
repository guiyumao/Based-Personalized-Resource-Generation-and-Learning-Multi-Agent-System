package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.LearningPathDto;
import com.softwarecompetition.agentcore.dto.LearningPathNodeDto;
import com.softwarecompetition.agentcore.dto.ResourceDto;
import com.softwarecompetition.agentcore.entity.*;
import com.softwarecompetition.agentcore.mapper.LearningPathMapper;
import com.softwarecompetition.agentcore.mapper.LearningPathNodeMapper;
import com.softwarecompetition.agentcore.mapper.ResourceMapper;
import com.softwarecompetition.agentcore.service.LearningPathService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class LearningPathServiceImpl implements LearningPathService {

    private static final Logger log = LoggerFactory.getLogger(LearningPathServiceImpl.class);

    private final DeepSeekClient deepSeekClient;
    private final UserProfileService userProfileService;
    private final LearningPathMapper pathMapper;
    private final LearningPathNodeMapper nodeMapper;
    private final ResourceMapper resourceMapper;
    private final ObjectMapper objectMapper;

    public LearningPathServiceImpl(DeepSeekClient deepSeekClient,
                                   UserProfileService userProfileService,
                                   LearningPathMapper pathMapper,
                                   LearningPathNodeMapper nodeMapper,
                                   ResourceMapper resourceMapper) {
        this.deepSeekClient = deepSeekClient;
        this.userProfileService = userProfileService;
        this.pathMapper = pathMapper;
        this.nodeMapper = nodeMapper;
        this.resourceMapper = resourceMapper;
        this.objectMapper = new ObjectMapper();
    }

    private static final String PATH_PROMPT =
        "你是一个个性化学习路径规划智能体。根据学生画像和知识水平，规划一个科学的学习路径。\n" +
        "学习路径应包含5-8个节点，从基础到进阶，逐步递进。每个节点包含：knowledgeId(英文标识)、title(中文标题)、\n" +
        "description(简短描述)、resourceTypeHint(建议资源类型)、estimatedTimeMinutes(预估分钟数)、\n" +
        "sortOrder(从1开始)。\n" +
        "只返回JSON（不要markdown包裹）:\n" +
        "{\"title\": \"路径标题\", \"description\": \"路径描述\", \"subject\": \"学科\", \"nodes\": [...]}";

    @Override
    public LearningPathDto generateLearningPath(Long userId) {
        UserProfile profile = userProfileService.getByUserId(userId);
        String profileStr = profile != null ?
            String.format("知识基础:%s, 学习风格:%s, 学习速度:%s, 兴趣方向:%s",
                profile.getKnowledgeBase(), profile.getCognitiveStyle(),
                profile.getLearningSpeed(), profile.getInterestDirection()) : "新学生";

        String response = deepSeekClient.chat(List.of(
            Map.of("role", "system", "content", PATH_PROMPT),
            Map.of("role", "user", "content", "学生画像：" + profileStr + "。请规划个性化学习路径。")
        ), 0.7);

        // 归档旧路径
        LambdaQueryWrapper<LearningPath> oldWrapper = new LambdaQueryWrapper<>();
        oldWrapper.eq(LearningPath::getUserId, userId).eq(LearningPath::getStatus, "active");
        List<LearningPath> oldPaths = pathMapper.selectList(oldWrapper);
        for (LearningPath old : oldPaths) {
            old.setStatus("archived");
            pathMapper.updateById(old);
        }

        try {
            String json = extractJson(response);
            var parsed = objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
            String title = (String) parsed.getOrDefault("title", "个性化学习路径");
            String desc = (String) parsed.getOrDefault("description", "");
            String subject = (String) parsed.getOrDefault("subject", "");

            LearningPath path = new LearningPath();
            path.setUserId(userId);
            path.setTitle(title);
            path.setDescription(desc);
            path.setSubject(subject);
            path.setStatus("active");

            @SuppressWarnings("unchecked")
            List<Map<String, Object>> nodes = (List<Map<String, Object>>) parsed.getOrDefault("nodes", List.of());
            path.setTotalNodes(nodes.size());
            path.setCompletedNodes(0);
            pathMapper.insert(path);

            List<LearningPathNodeDto> nodeDtos = new ArrayList<>();
            for (Map<String, Object> nodeData : nodes) {
                LearningPathNode node = new LearningPathNode();
                node.setLearningPathId(path.getId());
                node.setKnowledgeId((String) nodeData.getOrDefault("knowledgeId", "topic"));
                node.setTitle((String) nodeData.getOrDefault("title", "未命名"));
                node.setDescription((String) nodeData.getOrDefault("description", ""));
                node.setResourceTypeHint((String) nodeData.getOrDefault("resourceTypeHint", "lecture"));
                node.setSortOrder(((Number) nodeData.getOrDefault("sortOrder", 1)).intValue());
                node.setEstimatedTimeMinutes(((Number) nodeData.getOrDefault("estimatedTimeMinutes", 30)).intValue());
                node.setStatus("pending");
                nodeMapper.insert(node);

                LearningPathNodeDto nd = new LearningPathNodeDto();
                nd.setId(node.getId());
                nd.setKnowledgeId(node.getKnowledgeId());
                nd.setTitle(node.getTitle());
                nd.setDescription(node.getDescription());
                nd.setResourceTypeHint(node.getResourceTypeHint());
                nd.setSortOrder(node.getSortOrder());
                nd.setEstimatedTimeMinutes(node.getEstimatedTimeMinutes());
                nd.setStatus(node.getStatus());
                nodeDtos.add(nd);
            }

            LearningPathDto result = new LearningPathDto();
            result.setId(path.getId());
            result.setTitle(title);
            result.setDescription(desc);
            result.setSubject(subject);
            result.setStatus("active");
            result.setTotalNodes(nodes.size());
            result.setCompletedNodes(0);
            result.setNodes(nodeDtos);
            result.setCreatedAt(path.getCreatedAt());
            return result;

        } catch (Exception e) {
            log.error("学习路径生成失败", e);
            return createFallbackPath(userId);
        }
    }

    @Override
    public LearningPathDto adjustPath(Long userId, Long nodeId, String action) {
        LearningPathNode node = nodeMapper.selectById(nodeId);
        if (node == null) return null;

        switch (action) {
            case "complete" -> node.setStatus("completed");
            case "skip" -> node.setStatus("skipped");
            case "reset" -> node.setStatus("pending");
        }
        node.setUpdatedAt(java.time.LocalDateTime.now());
        nodeMapper.updateById(node);

        // 更新路径完成计数
        LearningPath path = pathMapper.selectById(node.getLearningPathId());
        if (path != null) {
            LambdaQueryWrapper<LearningPathNode> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(LearningPathNode::getLearningPathId, path.getId())
                    .eq(LearningPathNode::getStatus, "completed");
            path.setCompletedNodes((int) nodeMapper.selectCount(wrapper).intValue());
            pathMapper.updateById(path);
        }

        return loadPathDto(node.getLearningPathId());
    }

    @Override
    public List<ResourceDto> getResourcesForNode(Long nodeId) {
        LearningPathNode node = nodeMapper.selectById(nodeId);
        if (node == null) return List.of();

        LambdaQueryWrapper<Resource> wrapper = new LambdaQueryWrapper<>();
        wrapper.like(Resource::getKnowledgePoint, node.getKnowledgeId())
                .orderByDesc(Resource::getCreatedAt);
        List<Resource> resources = resourceMapper.selectList(wrapper);

        List<ResourceDto> dtos = new ArrayList<>();
        for (Resource r : resources) {
            ResourceDto dto = new ResourceDto();
            dto.setId(r.getId());
            dto.setResourceType(r.getResourceType());
            dto.setTitle(r.getTitle());
            dto.setKnowledgePoint(r.getKnowledgePoint());
            dto.setDifficultyLevel(r.getDifficultyLevel());
            dto.setEstimatedTimeMinutes(r.getEstimatedTimeMinutes());
            dto.setStatus(r.getStatus());
            dto.setCreatedAt(r.getCreatedAt());
            dtos.add(dto);
        }
        return dtos;
    }

    private LearningPathDto createFallbackPath(Long userId) {
        LearningPath path = new LearningPath();
        path.setUserId(userId);
        path.setTitle("基础学习路径");
        path.setStatus("active");
        path.setTotalNodes(3);
        path.setCompletedNodes(0);
        pathMapper.insert(path);

        String[][] defaultNodes = {
            {"basics", "基础知识巩固", "复习核心概念", "lecture", "1", "30"},
            {"practice", "实践练习", "通过练习加深理解", "exercise", "2", "45"},
            {"advanced", "进阶学习", "深入探索高级主题", "extended_reading", "3", "40"}
        };

        List<LearningPathNodeDto> nodeDtos = new ArrayList<>();
        for (String[] nd : defaultNodes) {
            LearningPathNode node = new LearningPathNode();
            node.setLearningPathId(path.getId());
            node.setKnowledgeId(nd[0]);
            node.setTitle(nd[1]);
            node.setDescription(nd[2]);
            node.setResourceTypeHint(nd[3]);
            node.setSortOrder(Integer.parseInt(nd[4]));
            node.setEstimatedTimeMinutes(Integer.parseInt(nd[5]));
            node.setStatus("pending");
            nodeMapper.insert(node);

            LearningPathNodeDto ndto = new LearningPathNodeDto();
            ndto.setId(node.getId());
            ndto.setKnowledgeId(nd[0]);
            ndto.setTitle(nd[1]);
            ndto.setDescription(nd[2]);
            ndto.setResourceTypeHint(nd[3]);
            ndto.setSortOrder(Integer.parseInt(nd[4]));
            ndto.setEstimatedTimeMinutes(Integer.parseInt(nd[5]));
            ndto.setStatus("pending");
            nodeDtos.add(ndto);
        }

        LearningPathDto result = new LearningPathDto();
        result.setId(path.getId());
        result.setTitle("基础学习路径");
        result.setStatus("active");
        result.setTotalNodes(3);
        result.setCompletedNodes(0);
        result.setNodes(nodeDtos);
        return result;
    }

    private LearningPathDto loadPathDto(Long pathId) {
        LearningPath path = pathMapper.selectById(pathId);
        if (path == null) return null;

        LambdaQueryWrapper<LearningPathNode> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningPathNode::getLearningPathId, pathId).orderByAsc(LearningPathNode::getSortOrder);
        List<LearningPathNode> nodes = nodeMapper.selectList(wrapper);

        List<LearningPathNodeDto> nodeDtos = new ArrayList<>();
        for (LearningPathNode n : nodes) {
            LearningPathNodeDto nd = new LearningPathNodeDto();
            nd.setId(n.getId());
            nd.setKnowledgeId(n.getKnowledgeId());
            nd.setTitle(n.getTitle());
            nd.setDescription(n.getDescription());
            nd.setResourceTypeHint(n.getResourceTypeHint());
            nd.setSortOrder(n.getSortOrder());
            nd.setEstimatedTimeMinutes(n.getEstimatedTimeMinutes());
            nd.setStatus(n.getStatus());
            nodeDtos.add(nd);
        }

        LearningPathDto result = new LearningPathDto();
        result.setId(path.getId());
        result.setTitle(path.getTitle());
        result.setDescription(path.getDescription());
        result.setSubject(path.getSubject());
        result.setStatus(path.getStatus());
        result.setTotalNodes(path.getTotalNodes());
        result.setCompletedNodes(path.getCompletedNodes());
        result.setNodes(nodeDtos);
        result.setCreatedAt(path.getCreatedAt());
        return result;
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
