package com.softwarecompetition.agentcore.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Setter
@Getter
@TableName("user_progress")
public class UserProgress {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String knowledgePoint;
    private BigDecimal masteryScore;
    private Integer totalTimeMinutes;
    private Integer exerciseCount;
    private Integer correctCount;
    private LocalDateTime lastActivityAt;
    @TableField("metadata_json")
    private String metadataJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
