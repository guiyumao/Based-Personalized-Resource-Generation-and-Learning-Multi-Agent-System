package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "异步资源生成任务状态")
public class ResourceTaskStatusResponse {

    @Schema(description = "任务ID")
    private Long taskId;

    @Schema(description = "任务状态：queued/processing/completed/failed")
    private String status;

    @Schema(description = "生成的资源ID（完成时有值）")
    private Long resourceId;

    @Schema(description = "提示信息")
    private String message;
}
