package com.education.agentservice.dto;

import java.util.List;
import java.util.Map;

public record CoordinationResponse(
    String status,
    List<String> selected_agents,
    String route_reason,
    Map<String, Object> outputs
) {
}
