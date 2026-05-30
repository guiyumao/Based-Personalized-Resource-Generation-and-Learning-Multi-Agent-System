package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

@Setter
@Getter
@Schema(description = "学习资源")
public class ResourceDto {

    @Schema(description = "资源ID")
    private Long id;

    @Schema(description = "资源类型")
    private String resourceType;

    @Schema(description = "标题")
    private String title;

    @Schema(description = "内容")
    private String content;

    @Schema(description = "格式")
    private String format;

    @Schema(description = "知识点")
    private String knowledgePoint;

    @Schema(description = "难度级别")
    private String difficultyLevel;

    @Schema(description = "预计学习时间（分钟）")
    private Integer estimatedTimeMinutes;

    @Schema(description = "状态")
    private String status;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
