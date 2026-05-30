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
@TableName("resource")
public class Resource {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String resourceType;
    private String title;
    private String content;
    private String format;
    private String knowledgePoint;
    private String difficultyLevel;
    private Integer estimatedTimeMinutes;
    private String tags;
    @TableField("metadata_json")
    private String metadataJson;
    private String status;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
