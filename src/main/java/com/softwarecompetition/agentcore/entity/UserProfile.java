package com.softwarecompetition.agentcore.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

@Setter
@Getter
@TableName("user_profile")
public class UserProfile {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String knowledgeBase;

    private String cognitiveStyle;

    private String errorPreference;

    private String learningSpeed;

    private String interestDirection;

    private String goalOrientation;

    @TableField("profile_json")
    private String profileJson;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

}
