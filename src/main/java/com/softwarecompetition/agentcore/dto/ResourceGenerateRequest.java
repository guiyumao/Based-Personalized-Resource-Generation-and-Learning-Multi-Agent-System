package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "资源生成请求")
public class ResourceGenerateRequest {

    @Schema(description = "用户自然语言需求描述", example = "我想学习Java并发编程的线程池原理")
    private String requestText;

    @Schema(description = "期望的资源类型（不指定则由智能体自动判断）", example = "lecture")
    private String resourceType;

    @Schema(description = "知识点名称", example = "Java线程池")
    private String knowledgePoint;
}
