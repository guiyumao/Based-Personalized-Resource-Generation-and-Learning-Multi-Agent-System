package com.softwarecompetition.agentcore.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

@Setter
@Getter
@TableName("learning_path")
public class LearningPath {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String title;
    private String description;
    private String subject;
    private String status;
    private Integer totalNodes;
    private Integer completedNodes;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
