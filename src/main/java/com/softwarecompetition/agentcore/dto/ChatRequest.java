package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
@Schema(description = "画像构建对话请求")
public class ChatRequest {

    @Schema(description = "用户ID", example = "1")
    private Long userId;

    @Schema(description = "用户发送的消息", example = "你好，我在学习Java，感觉并发编程很难")
    private String message;
}
