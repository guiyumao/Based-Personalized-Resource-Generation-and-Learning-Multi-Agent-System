package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.List;
import java.util.Map;

@Setter
@Getter
@Schema(description = "六维度雷达图数据")
public class RadarChartDto {

    @Schema(description = "维度标签列表")
    private List<String> labels;

    @Schema(description = "各维度分值（0-100）")
    private List<Integer> scores;

    @Schema(description = "维度详细数据")
    private List<Map<String, Object>> details;
}
