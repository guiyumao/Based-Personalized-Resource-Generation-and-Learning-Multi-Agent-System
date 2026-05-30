package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.mapper.UserProfileMapper;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.Map;

@Service
public class UserProfileServiceImpl extends ServiceImpl<UserProfileMapper, UserProfile> implements UserProfileService {

    @Override
    @Cacheable(value = "profile", key = "#userId", unless = "#result == null")
    public UserProfile getByUserId(Long userId) {
        LambdaQueryWrapper<UserProfile> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(UserProfile::getUserId, userId);
        return getOne(wrapper);
    }

    @Override
    @CacheEvict(value = "profile", key = "#userId")
    public UserProfile createOrUpdate(Long userId, Map<String, String> dimensions) {
        UserProfile existing = getByUserId(userId);
        UserProfile profile = existing != null ? existing : new UserProfile();

        profile.setUserId(userId);

        if (dimensions.containsKey("knowledgeBase"))
            profile.setKnowledgeBase(dimensions.get("knowledgeBase"));
        if (dimensions.containsKey("cognitiveStyle"))
            profile.setCognitiveStyle(dimensions.get("cognitiveStyle"));
        if (dimensions.containsKey("errorPreference"))
            profile.setErrorPreference(dimensions.get("errorPreference"));
        if (dimensions.containsKey("learningSpeed"))
            profile.setLearningSpeed(dimensions.get("learningSpeed"));
        if (dimensions.containsKey("interestDirection"))
            profile.setInterestDirection(dimensions.get("interestDirection"));
        if (dimensions.containsKey("goalOrientation"))
            profile.setGoalOrientation(dimensions.get("goalOrientation"));

        profile.setUpdatedAt(LocalDateTime.now());

        if (existing != null) {
            updateById(profile);
        } else {
            save(profile);
        }

        return profile;
    }
}
