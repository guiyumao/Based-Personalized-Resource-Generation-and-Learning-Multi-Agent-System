package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "学习路径节点")
public class LearningPathNodeDto {

    @Schema(description = "节点ID")
    private Long id;

    @Schema(description = "父节点ID")
    private Long parentNodeId;

    @Schema(description = "知识点标识")
    private String knowledgeId;

    @Schema(description = "节点标题")
    private String title;

    @Schema(description = "描述")
    private String description;

    @Schema(description = "建议资源类型")
    private String resourceTypeHint;

    @Schema(description = "排序序号")
    private Integer sortOrder;

    @Schema(description = "预计学习时间（分钟）")
    private Integer estimatedTimeMinutes;

    @Schema(description = "节点状态")
    private String status;

    @Schema(description = "关联资源ID列表")
    private String resourceIds;
}
