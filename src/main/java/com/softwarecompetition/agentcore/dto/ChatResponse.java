package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.Map;

@Setter
@Getter
@Schema(description = "画像构建对话响应")
public class ChatResponse {

    @Schema(description = "智能体的自然语言回复")
    private String reply;

    @Schema(description = "本轮对话中提取到的画像维度更新，key为维度英文名，value为提取的值；无更新时为空对象")
    private Map<String, String> profileUpdates;

    @Schema(description = "六维度完整度状态，如 {\"knowledgeBase\":\"已获取\", \"cognitiveStyle\":\"未获取\", ...}")
    private Map<String, String> profileCompleteness;

    @Schema(description = "预估还需多少轮对话完成画像，0表示构建完成", example = "3")
    private Integer estimatedRemainingRounds;
}
