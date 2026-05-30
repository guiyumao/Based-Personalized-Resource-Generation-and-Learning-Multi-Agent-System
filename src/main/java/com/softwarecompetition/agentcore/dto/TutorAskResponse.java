package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Setter
@Getter
@Schema(description = "智能辅导回答响应")
public class TutorAskResponse {

    @Schema(description = "回答内容")
    private String answer;

    @Schema(description = "检索到的知识库上下文片段（调试用）")
    private List<String> contextSnippets;

    @Schema(description = "置信度（0-1）")
    private Double confidence;
}
