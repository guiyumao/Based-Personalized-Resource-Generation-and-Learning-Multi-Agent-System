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
@TableName("knowledge_base")
public class KnowledgeBase {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String title;
    private String content;
    private String contentType;
    private String knowledgePoint;
    private String tags;
    private String source;
    @TableField("embedding")
    private String embedding;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
