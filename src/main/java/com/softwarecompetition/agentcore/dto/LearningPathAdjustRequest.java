package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "学习路径调整请求")
public class LearningPathAdjustRequest {

    @Schema(description = "节点ID", example = "2")
    private Long nodeId;

    @Schema(description = "操作：skip(跳过) / complete(标记完成) / reset(重置)", example = "complete")
    private String action;
}
