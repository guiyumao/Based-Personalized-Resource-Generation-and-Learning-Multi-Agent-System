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
@TableName("learning_path_node")
public class LearningPathNode {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long learningPathId;
    private Long parentNodeId;
    private String knowledgeId;
    private String title;
    private String description;
    private String resourceTypeHint;
    private Integer sortOrder;
    private Integer estimatedTimeMinutes;
    private String status;
    private String resourceIds;
    @TableField("metadata_json")
    private String metadataJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
