package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Setter
@Getter
@Schema(description = "学习效果评估报告")
public class AnalyticsReportDto {

    @Schema(description = "总学习时长（分钟）")
    private Integer totalStudyMinutes;

    @Schema(description = "资源学习数量")
    private Integer resourceCount;

    @Schema(description = "练习题数量")
    private Integer exerciseCount;

    @Schema(description = "正确率（0-100）")
    private BigDecimal correctRate;

    @Schema(description = "各知识点掌握度")
    private List<Map<String, Object>> masteryByKnowledgePoint;

    @Schema(description = "每周学习活动统计")
    private List<Map<String, Object>> weeklyActivity;
}
