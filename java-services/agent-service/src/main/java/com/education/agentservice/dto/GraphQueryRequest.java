package com.education.agentservice.dto;

public record GraphQueryRequest(
    String knowledge_point,
    Integer max_depth
) {
}
