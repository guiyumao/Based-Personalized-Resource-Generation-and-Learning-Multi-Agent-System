package com.softwarecompetition.agentcore.controller;

import com.softwarecompetition.agentcore.dto.*;
import com.softwarecompetition.agentcore.service.LearningPathService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(name = "学习路径", description = "个性化学习路径规划、手动调整与资源推送")
@RestController
@RequestMapping("/api/learning-path")
public class LearningPathController {

    private final LearningPathService learningPathService;

    public LearningPathController(LearningPathService learningPathService) {
        this.learningPathService = learningPathService;
    }

    @Operation(summary = "获取/生成个性化学习路径", description = "基于用户画像自动规划学习路径，已有活跃路径则直接返回")
    @GetMapping
    public ResponseEntity<LearningPathDto> getLearningPath(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId) {
        LearningPathDto path = learningPathService.generateLearningPath(userId);
        return ResponseEntity.ok(path);
    }

    @Operation(summary = "手动调整学习路径", description = "标记节点为完成/跳过/重置")
    @PostMapping(value = "/adjust", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<LearningPathDto> adjustPath(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @RequestBody LearningPathAdjustRequest request) {
        if (request.getNodeId() == null || request.getAction() == null) {
            return ResponseEntity.badRequest().build();
        }
        LearningPathDto path = learningPathService.adjustPath(userId, request.getNodeId(), request.getAction());
        return path != null ? ResponseEntity.ok(path) : ResponseEntity.notFound().build();
    }

    @Operation(summary = "获取指定知识点的推送资源", description = "根据学习路径节点的知识点获取相关资源列表")
    @GetMapping("/resources/{nodeId}")
    public ResponseEntity<List<ResourceDto>> getResourcesForNode(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @PathVariable Long nodeId) {
        return ResponseEntity.ok(learningPathService.getResourcesForNode(nodeId));
    }
}
