package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "学习进度上报请求")
public class ResourceProgressRequest {

    @Schema(description = "资源ID", example = "1")
    private Long resourceId;

    @Schema(description = "学习动作", example = "reading")
    private String action;

    @Schema(description = "进度百分比（0-100）", example = "60")
    private Integer progressPercent;

    @Schema(description = "本次学习时长（秒）", example = "300")
    private Integer timeSpentSeconds;
}
