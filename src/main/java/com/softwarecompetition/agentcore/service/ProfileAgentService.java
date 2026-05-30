package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.ChatResponse;

public interface ProfileAgentService {

    ChatResponse chat(Long userId, String message);
}
