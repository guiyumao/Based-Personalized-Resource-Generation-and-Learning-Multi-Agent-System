package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "资源生成响应")
public class ResourceGenerateResponse {

    @Schema(description = "生成的资源ID")
    private Long resourceId;

    @Schema(description = "资源类型")
    private String resourceType;

    @Schema(description = "资源标题")
    private String title;

    @Schema(description = "生成状态")
    private String status;

    @Schema(description = "提示信息")
    private String message;
}
