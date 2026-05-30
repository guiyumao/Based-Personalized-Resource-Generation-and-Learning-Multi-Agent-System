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
@TableName("learning_record")
public class LearningRecord {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long resourceId;
    private String action;
    private BigDecimal score;
    private Integer progressPercent;
    private Integer timeSpentSeconds;
    @TableField("metadata_json")
    private String metadataJson;
    private LocalDateTime createdAt;
}
