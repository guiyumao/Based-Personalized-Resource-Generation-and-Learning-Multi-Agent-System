package com.education.agentservice.dto;

import java.util.Map;

public record ResourceGenerationRequest(
    Long user_id,
    String knowledge_point,
    String resource_style,
    String resource_type,
    Map<String, Object> learner_profile
) {
}
