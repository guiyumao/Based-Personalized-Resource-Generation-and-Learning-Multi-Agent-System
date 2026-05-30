package com.softwarecompetition.agentcore.controller;

import com.softwarecompetition.agentcore.dto.*;
import com.softwarecompetition.agentcore.entity.LearningRecord;
import com.softwarecompetition.agentcore.entity.ResourceGenerationRecord;
import com.softwarecompetition.agentcore.mapper.LearningRecordMapper;
import com.softwarecompetition.agentcore.mapper.ResourceGenerationRecordMapper;
import com.softwarecompetition.agentcore.service.ResourceCoordinationService;
import com.softwarecompetition.agentcore.service.ScoringService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(name = "资源生成", description = "多智能体协同资源生成：异步生成、历史查询、进度上报")
@RestController
@RequestMapping("/api/resource")
public class ResourceController {

    private final ResourceCoordinationService coordinationService;
    private final ResourceGenerationRecordMapper recordMapper;
    private final LearningRecordMapper learningRecordMapper;
    private final ScoringService scoringService;

    public ResourceController(ResourceCoordinationService coordinationService,
                               ResourceGenerationRecordMapper recordMapper,
                               LearningRecordMapper learningRecordMapper,
                               ScoringService scoringService) {
        this.coordinationService = coordinationService;
        this.recordMapper = recordMapper;
        this.learningRecordMapper = learningRecordMapper;
        this.scoringService = scoringService;
    }

    @Operation(summary = "请求生成资源（异步）", description = "传入自然语言需求，返回任务ID。资源在后台异步生成，通过状态接口查询进度")
    @PostMapping(value = "/generate", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ResourceGenerateResponse> generate(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @RequestBody ResourceGenerateRequest request) {
        if (request.getRequestText() == null || request.getRequestText().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        ResourceGenerateResponse response = coordinationService.generate(userId, request);
        return ResponseEntity.ok(response);
    }

    @Operation(summary = "查询生成任务状态", description = "轮询异步资源生成任务的进度")
    @GetMapping("/generate/{taskId}/status")
    public ResponseEntity<ResourceTaskStatusResponse> getTaskStatus(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @PathVariable Long taskId) {
        ResourceTaskStatusResponse status = coordinationService.getTaskStatus(taskId);
        return ResponseEntity.ok(status);
    }

    @Operation(summary = "获取生成历史", description = "分页查询用户的历史资源生成记录")
    @GetMapping("/history")
    public ResponseEntity<List<ResourceDto>> getHistory(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(coordinationService.getHistory(userId, page, size));
    }

    @Operation(summary = "获取资源详情", description = "获取指定资源的完整内容")
    @GetMapping("/{resourceId}")
    public ResponseEntity<ResourceDto> getResource(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @PathVariable Long resourceId) {
        ResourceDto resource = coordinationService.getResource(resourceId);
        return resource != null ? ResponseEntity.ok(resource) : ResponseEntity.notFound().build();
    }

    @Operation(summary = "上报学习进度", description = "前端定时上报资源学习进度，自动触发画像评分更新")
    @PostMapping(value = "/progress", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> reportProgress(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @RequestBody ResourceProgressRequest request) {
        LearningRecord record = new LearningRecord();
        record.setUserId(userId);
        record.setResourceId(request.getResourceId());
        record.setAction(request.getAction());
        record.setProgressPercent(request.getProgressPercent());
        record.setTimeSpentSeconds(request.getTimeSpentSeconds());
        learningRecordMapper.insert(record);

        // 异步更新画像评分
        try {
            scoringService.updateUserProgress(userId);
        } catch (Exception e) {
            // 评分更新失败不影响主流程
            log.warn("评分更新失败: userId={}", userId, e);
        }

        return ResponseEntity.ok().build();
    }

    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(ResourceController.class);
}
