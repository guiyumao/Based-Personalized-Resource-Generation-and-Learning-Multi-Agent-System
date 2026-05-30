package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.List;

@Setter
@Getter
@Schema(description = "学习路径")
public class LearningPathDto {

    @Schema(description = "路径ID")
    private Long id;

    @Schema(description = "标题")
    private String title;

    @Schema(description = "描述")
    private String description;

    @Schema(description = "学科")
    private String subject;

    @Schema(description = "状态")
    private String status;

    @Schema(description = "总节点数")
    private Integer totalNodes;

    @Schema(description = "已完成节点数")
    private Integer completedNodes;

    @Schema(description = "节点列表")
    private List<LearningPathNodeDto> nodes;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
