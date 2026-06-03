package com.education.agentservice.dto;

import java.util.Map;

public record LearningPathRequest(
    Long user_id,
    String subject,
    String knowledge_point,
    Integer daily_minutes,
    Map<String, Object> learner_profile
) {
}
