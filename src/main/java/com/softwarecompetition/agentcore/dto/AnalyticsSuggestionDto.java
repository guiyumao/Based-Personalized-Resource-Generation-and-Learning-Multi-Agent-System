package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Setter
@Getter
@Schema(description = "AI学习建议")
public class AnalyticsSuggestionDto {

    @Schema(description = "建议列表")
    private List<String> suggestions;

    @Schema(description = "需重点关注的知识领域")
    private List<String> focusAreas;

    @Schema(description = "推荐资源ID列表")
    private List<Long> recommendedResourceIds;
}
