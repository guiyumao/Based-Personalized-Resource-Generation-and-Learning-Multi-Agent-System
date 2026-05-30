package com.softwarecompetition.agentcore.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.softwarecompetition.agentcore.entity.ProfileConversation;

import java.util.List;

public interface ProfileConversationService extends IService<ProfileConversation> {

    List<ProfileConversation> getHistoryByUserId(Long userId, int limit);

    ProfileConversation saveMessage(Long userId, String role, String content);
}
