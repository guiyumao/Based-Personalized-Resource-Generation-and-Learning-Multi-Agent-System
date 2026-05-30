package com.softwarecompetition.agentcore.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.softwarecompetition.agentcore.entity.UserProfile;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserProfileMapper extends BaseMapper<UserProfile> {
}
