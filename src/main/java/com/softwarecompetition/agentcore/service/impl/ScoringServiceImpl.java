package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.softwarecompetition.agentcore.entity.LearningRecord;
import com.softwarecompetition.agentcore.entity.Resource;
import com.softwarecompetition.agentcore.entity.UserProgress;
import com.softwarecompetition.agentcore.mapper.LearningRecordMapper;
import com.softwarecompetition.agentcore.mapper.ResourceMapper;
import com.softwarecompetition.agentcore.mapper.UserProgressMapper;
import com.softwarecompetition.agentcore.service.ScoringService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

@Service
public class ScoringServiceImpl implements ScoringService {

    private static final Logger log = LoggerFactory.getLogger(ScoringServiceImpl.class);

    // 默认掌握度（无答题记录时）
    private static final int DEFAULT_MASTERY = 62;

    private final LearningRecordMapper recordMapper;
    private final ResourceMapper resourceMapper;
    private final UserProgressMapper progressMapper;

    public ScoringServiceImpl(LearningRecordMapper recordMapper,
                              ResourceMapper resourceMapper,
                              UserProgressMapper progressMapper) {
        this.recordMapper = recordMapper;
        this.resourceMapper = resourceMapper;
        this.progressMapper = progressMapper;
    }

    @Override
    public void updateUserProgress(Long userId) {
        // 获取该用户所有学习记录
        LambdaQueryWrapper<LearningRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningRecord::getUserId, userId);
        List<LearningRecord> records = recordMapper.selectList(wrapper);

        if (records.isEmpty()) return;

        // 按知识点聚合
        Map<String, List<LearningRecord>> byKnowledge = new HashMap<>();
        for (LearningRecord r : records) {
            if (r.getResourceId() == null) continue;
            Resource resource = resourceMapper.selectById(r.getResourceId());
            String kp = resource != null && resource.getKnowledgePoint() != null
                    ? resource.getKnowledgePoint() : "通用";
            byKnowledge.computeIfAbsent(kp, k -> new ArrayList<>()).add(r);
        }

        // 对每个知识点计算掌握度
        for (Map.Entry<String, List<LearningRecord>> entry : byKnowledge.entrySet()) {
            String kp = entry.getKey();
            List<LearningRecord> kpRecords = entry.getValue();

            int mastery = estimateMastery(kpRecords);
            int exerciseCount = (int) kpRecords.stream()
                    .filter(r -> r.getScore() != null).count();
            int correctCount = (int) kpRecords.stream()
                    .filter(r -> r.getScore() != null && r.getScore().compareTo(new BigDecimal("60")) >= 0)
                    .count();
            int totalMinutes = kpRecords.stream()
                    .mapToInt(r -> r.getTimeSpentSeconds() != null ? r.getTimeSpentSeconds() / 60 : 0)
                    .sum();

            // 更新 user_progress
            LambdaQueryWrapper<UserProgress> pw = new LambdaQueryWrapper<>();
            pw.eq(UserProgress::getUserId, userId).eq(UserProgress::getKnowledgePoint, kp);
            UserProgress progress = progressMapper.selectOne(pw);

            if (progress == null) {
                progress = new UserProgress();
                progress.setUserId(userId);
                progress.setKnowledgePoint(kp);
            }
            progress.setMasteryScore(BigDecimal.valueOf(mastery));
            progress.setExerciseCount(exerciseCount);
            progress.setCorrectCount(correctCount);
            progress.setTotalTimeMinutes(totalMinutes);
            progress.setLastActivityAt(LocalDateTime.now());

            if (progress.getId() != null) {
                progressMapper.updateById(progress);
            } else {
                progressMapper.insert(progress);
            }
        }

        log.info("用户{}评分更新完成，涉及{}个知识点", userId, byKnowledge.size());
    }

    @Override
    public int calculateMastery(Long userId, String knowledgePoint) {
        LambdaQueryWrapper<LearningRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(LearningRecord::getUserId, userId);
        List<LearningRecord> all = recordMapper.selectList(wrapper);

        List<LearningRecord> filtered = all.stream()
                .filter(r -> {
                    if (r.getResourceId() == null) return false;
                    Resource resource = resourceMapper.selectById(r.getResourceId());
                    return resource != null && knowledgePoint.equals(resource.getKnowledgePoint());
                })
                .collect(Collectors.toList());

        if (filtered.isEmpty()) return DEFAULT_MASTERY;
        return estimateMastery(filtered);
    }

    /**
     * 核心评分算法：基础分 + 速度修正 + 难度修正 → 加权平均
     */
    private int estimateMastery(List<LearningRecord> records) {
        if (records.isEmpty()) return DEFAULT_MASTERY;

        // 按时间排序，越近权重越高
        records.sort(Comparator.comparing(LearningRecord::getCreatedAt,
                Comparator.nullsLast(Comparator.naturalOrder())));

        double totalWeight = 0;
        double weightedSum = 0;

        for (int i = 0; i < records.size(); i++) {
            LearningRecord r = records.get(i);
            // 近期记录权重更高（线性递增：第一个权重1，最后一个权重N）
            double weight = i + 1.0;
            totalWeight += weight;

            // 基础分：60为及格线
            double base = r.getScore() != null ? r.getScore().doubleValue() : 50;

            // 速度修正：时间越短越快越好（秒转分钟）
            double speedBonus = 0;
            if (r.getTimeSpentSeconds() != null && r.getTimeSpentSeconds() > 0) {
                double minutes = r.getTimeSpentSeconds() / 60.0;
                // 目标时间5分钟，快加分慢扣分，限制在[-10, +8]
                speedBonus = Math.max(-10, Math.min(8, 5 - minutes));
            }

            // 难度修正：从resource获取
            double diffBonus = 0;
            if (r.getResourceId() != null) {
                Resource resource = resourceMapper.selectById(r.getResourceId());
                if (resource != null) {
                    diffBonus = switch (resource.getDifficultyLevel()) {
                        case "easy", "foundation" -> 0;
                        case "medium", "intermediate" -> 4;
                        case "hard", "advanced" -> 8;
                        default -> 0;
                    };
                }
            }

            double score = Math.max(0, Math.min(100, base + speedBonus + diffBonus));
            weightedSum += score * weight;
        }

        return (int) Math.round(weightedSum / totalWeight);
    }
}
