package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.ResourceGenerateRequest;
import com.softwarecompetition.agentcore.dto.ResourceGenerateResponse;
import com.softwarecompetition.agentcore.dto.ResourceDto;
import com.softwarecompetition.agentcore.dto.ResourceTaskStatusResponse;

import java.util.List;

public interface ResourceCoordinationService {

    ResourceGenerateResponse generate(Long userId, ResourceGenerateRequest request);

    void executeGeneration(Long taskId, Long userId, ResourceGenerateRequest request);

    ResourceTaskStatusResponse getTaskStatus(Long taskId);

    List<ResourceDto> getHistory(Long userId, int page, int size);

    ResourceDto getResource(Long resourceId);
}
