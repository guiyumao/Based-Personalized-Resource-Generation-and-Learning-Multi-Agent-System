package com.education.userservice.dto;

import java.util.List;

public record LearnerProfileDashboardResponse(
    Long userId,
    String learningStyle,
    Integer masteryOverview,
    Integer weeklyFocusMinutes,
    String habitSummary,
    List<MetricItem> radarMetrics,
    List<HeatmapItem> heatmap
) {
    public record MetricItem(String dimension, Integer score) {}
    public record HeatmapItem(String knowledgePoint, Integer mastery) {}
}
