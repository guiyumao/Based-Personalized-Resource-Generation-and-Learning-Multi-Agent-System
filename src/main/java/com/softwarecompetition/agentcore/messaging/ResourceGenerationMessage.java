package com.softwarecompetition.agentcore.messaging;

import java.io.Serializable;

public class ResourceGenerationMessage implements Serializable {

    private Long taskId;
    private Long userId;
    private String requestText;
    private String resourceType;
    private String knowledgePoint;

    public ResourceGenerationMessage() {}

    public ResourceGenerationMessage(Long taskId, Long userId, String requestText,
                                      String resourceType, String knowledgePoint) {
        this.taskId = taskId;
        this.userId = userId;
        this.requestText = requestText;
        this.resourceType = resourceType;
        this.knowledgePoint = knowledgePoint;
    }

    public Long getTaskId() { return taskId; }
    public void setTaskId(Long taskId) { this.taskId = taskId; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getRequestText() { return requestText; }
    public void setRequestText(String requestText) { this.requestText = requestText; }

    public String getResourceType() { return resourceType; }
    public void setResourceType(String resourceType) { this.resourceType = resourceType; }

    public String getKnowledgePoint() { return knowledgePoint; }
    public void setKnowledgePoint(String knowledgePoint) { this.knowledgePoint = knowledgePoint; }
}
