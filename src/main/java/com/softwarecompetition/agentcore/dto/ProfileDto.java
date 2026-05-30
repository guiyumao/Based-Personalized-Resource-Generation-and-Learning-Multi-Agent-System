package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.Map;

@Setter
@Getter
@Schema(description = "用户画像数据")
public class ProfileDto {

    @Schema(description = "用户ID", example = "1")
    private Long userId;

    @Schema(description = "知识基础", example = "Java基础")
    private String knowledgeBase;

    @Schema(description = "认知风格", example = "动手实践型")
    private String cognitiveStyle;

    @Schema(description = "易错点偏好", example = "并发编程")
    private String errorPreference;

    @Schema(description = "学习节奏", example = "适中")
    private String learningSpeed;

    @Schema(description = "兴趣方向", example = "后端开发")
    private String interestDirection;

    @Schema(description = "学习目标", example = "找到Java后端实习")
    private String goalOrientation;

    @Schema(description = "扩展画像JSON")
    private Map<String, Object> profileJson;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
