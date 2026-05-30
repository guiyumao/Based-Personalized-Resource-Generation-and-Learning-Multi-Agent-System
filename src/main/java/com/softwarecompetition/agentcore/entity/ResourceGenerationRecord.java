package com.softwarecompetition.agentcore.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

@Setter
@Getter
@TableName("resource_generation_record")
public class ResourceGenerationRecord {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long resourceId;
    private String requestText;
    private String resourceType;
    private String knowledgePoint;
    private String status;
    private String errorMessage;
    private Integer tokensUsed;
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
}
