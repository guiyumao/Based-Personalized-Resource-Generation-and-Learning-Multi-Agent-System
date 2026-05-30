package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.LearningPathDto;
import com.softwarecompetition.agentcore.dto.ResourceDto;

import java.util.List;

public interface LearningPathService {

    LearningPathDto generateLearningPath(Long userId);

    LearningPathDto adjustPath(Long userId, Long nodeId, String action);

    List<ResourceDto> getResourcesForNode(Long nodeId);
}
