package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Setter
@Getter
@Schema(description = "资源生成方案")
public class GenerationPlan {

    @Schema(description = "资源类型", example = "lecture")
    private String resourceType;

    @Schema(description = "知识点", example = "Redis基础")
    private String knowledgePoint;

    @Schema(description = "建议章节大纲")
    private List<String> suggestedOutline;

    @Schema(description = "建议字数", example = "5000")
    private Integer wordCount;

    @Schema(description = "难度", example = "medium")
    private String difficulty;

    @Schema(description = "呈现风格", example = "interactive")
    private String style;

    @Schema(description = "个性化提示（基于画像的针对性建议）")
    private String personalizationHints;

    @Schema(description = "建议标题")
    private String titleSuggestion;
}
