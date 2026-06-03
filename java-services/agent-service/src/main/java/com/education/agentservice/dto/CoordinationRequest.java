package com.education.agentservice.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record CoordinationRequest(
    Long user_id,
    @NotBlank String intent,
    String knowledge_point,
    Map<String, Object> payload
) {
}
