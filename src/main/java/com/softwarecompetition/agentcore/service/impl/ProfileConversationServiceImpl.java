package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.softwarecompetition.agentcore.entity.ProfileConversation;
import com.softwarecompetition.agentcore.mapper.ProfileConversationMapper;
import com.softwarecompetition.agentcore.service.ProfileConversationService;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ProfileConversationServiceImpl extends ServiceImpl<ProfileConversationMapper, ProfileConversation> implements ProfileConversationService {

    @Override
    public List<ProfileConversation> getHistoryByUserId(Long userId, int limit) {
        LambdaQueryWrapper<ProfileConversation> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(ProfileConversation::getUserId, userId)
                .orderByAsc(ProfileConversation::getCreatedAt);
        // 对话历史通常不会太长，全量查出后在内存中截取，避免SQL方言兼容问题
        List<ProfileConversation> list = list(wrapper);
        int from = Math.max(0, list.size() - limit);
        return list.subList(from, list.size());
    }

    @Override
    public ProfileConversation saveMessage(Long userId, String role, String content) {
        ProfileConversation conversation = new ProfileConversation();
        conversation.setUserId(userId);
        conversation.setRole(role);
        conversation.setContent(content);
        save(conversation);
        return conversation;
    }
}
