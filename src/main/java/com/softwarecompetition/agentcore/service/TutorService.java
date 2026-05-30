package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.dto.TutorAskRequest;
import com.softwarecompetition.agentcore.dto.TutorAskResponse;

public interface TutorService {

    TutorAskResponse ask(Long userId, TutorAskRequest request);
}
