package com.education.agentservice.dto;

import java.util.Map;

public record ExerciseGenerationRequest(
    Long user_id,
    String knowledge_point,
    String resource_style,
    Map<String, Object> learner_profile,
    Integer exercise_count,
    String generation_mode,
    String courseware_content
) {
}
