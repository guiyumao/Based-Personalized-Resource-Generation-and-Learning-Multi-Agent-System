package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.GenerationPlan;
import com.softwarecompetition.agentcore.entity.Resource;

public interface ResourceGenerationService {

    Resource generateResource(Long userId, GenerationPlan plan, String userRequest);
}
