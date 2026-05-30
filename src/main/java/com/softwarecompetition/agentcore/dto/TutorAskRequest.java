package com.softwarecompetition.agentcore.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Setter
@Getter
@Schema(description = "智能辅导提问请求")
public class TutorAskRequest {

    @Schema(description = "学生提问内容", example = "什么是Java线程池？它的核心参数有哪些？")
    private String question;

    @Schema(description = "可选的图片URL列表（多模态支持）")
    private List<String> imageUrls;
}
