package com.softwarecompetition.agentcore.controller;

import com.softwarecompetition.agentcore.dto.AnalyticsReportDto;
import com.softwarecompetition.agentcore.dto.AnalyticsSuggestionDto;
import com.softwarecompetition.agentcore.dto.RadarChartDto;
import com.softwarecompetition.agentcore.service.AnalyticsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Tag(name = "学习分析", description = "多维度学习效果评估、雷达图与AI建议（加分项）")
@RestController
@RequestMapping("/api/analytics")
public class AnalyticsController {

    private final AnalyticsService analyticsService;

    public AnalyticsController(AnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }

    @Operation(summary = "获取评估报告", description = "多维度学习效果评估报告")
    @GetMapping("/report")
    public ResponseEntity<AnalyticsReportDto> getReport(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId) {
        return ResponseEntity.ok(analyticsService.getReport(userId));
    }

    @Operation(summary = "获取雷达图数据", description = "六维度能力雷达图")
    @GetMapping("/radar")
    public ResponseEntity<RadarChartDto> getRadar(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId) {
        return ResponseEntity.ok(analyticsService.getRadarChartData(userId));
    }

    @Operation(summary = "获取AI学习建议", description = "基于学习数据分析的个性化改进建议")
    @GetMapping("/suggestion")
    public ResponseEntity<AnalyticsSuggestionDto> getSuggestion(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId) {
        return ResponseEntity.ok(analyticsService.getSuggestion(userId));
    }
}
