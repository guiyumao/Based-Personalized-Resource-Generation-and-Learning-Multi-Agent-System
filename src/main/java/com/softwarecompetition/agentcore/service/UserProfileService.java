package com.softwarecompetition.agentcore.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.softwarecompetition.agentcore.entity.UserProfile;

import java.util.Map;

public interface UserProfileService extends IService<UserProfile> {

    UserProfile getByUserId(Long userId);

    UserProfile createOrUpdate(Long userId, Map<String, String> dimensions);
}
