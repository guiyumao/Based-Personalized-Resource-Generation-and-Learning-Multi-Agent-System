package com.softwarecompetition.agentcore.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

@Setter
@Getter
@TableName("profile_conversation")
public class ProfileConversation {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String role;

    private String content;

    private LocalDateTime createdAt;

}
