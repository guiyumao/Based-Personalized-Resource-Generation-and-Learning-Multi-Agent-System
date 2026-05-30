package com.softwarecompetition.agentcore.service;

public interface ScoringService {

    /**
     * 更新指定用户的所有知识点掌握度评分
     */
    void updateUserProgress(Long userId);

    /**
     * 根据答题记录计算单个知识点的掌握度（0-100）
     */
    int calculateMastery(Long userId, String knowledgePoint);
}
