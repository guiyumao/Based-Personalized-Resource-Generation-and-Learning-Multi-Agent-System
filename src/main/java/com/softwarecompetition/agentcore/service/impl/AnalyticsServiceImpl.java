package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.AnalyticsReportDto;
import com.softwarecompetition.agentcore.dto.AnalyticsSuggestionDto;
import com.softwarecompetition.agentcore.dto.RadarChartDto;
import com.softwarecompetition.agentcore.entity.*;
import com.softwarecompetition.agentcore.mapper.LearningRecordMapper;
import com.softwarecompetition.agentcore.mapper.ResourceMapper;
import com.softwarecompetition.agentcore.mapper.UserProgressMapper;
import com.softwarecompetition.agentcore.service.AnalyticsService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;

@Service
public class AnalyticsServiceImpl implements AnalyticsService {

    private static final Logger log = LoggerFactory.getLogger(AnalyticsServiceImpl.class);

    private final UserProfileService userProfileService;
    private final UserProgressMapper progressMapper;
    private final LearningRecordMapper recordMapper;
    private final ResourceMapper resourceMapper;
    private final DeepSeekClient deepSeekClient;
    private final ObjectMapper objectMapper;

    public AnalyticsServiceImpl(UserProfileService userProfileService,
                                UserProgressMapper progressMapper,
                                LearningRecordMapper recordMapper,
                                ResourceMapper resourceMapper,
                                DeepSeekClient deepSeekClient) {
        this.userProfileService = userProfileService;
        this.progressMapper = progressMapper;
        this.recordMapper = recordMapper;
        this.resourceMapper = resourceMapper;
        this.deepSeekClient = deepSeekClient;
        this.objectMapper = new ObjectMapper();
    }

    private static final String SUGGESTION_PROMPT =
        "你是一个学习效果评估智能体。根据学生的学习数据，给出个性化改进建议。\n" +
        "分析：弱项知识点、学习效率、练习正确率趋势。\n" +
        "返回JSON（不要markdown包裹）:\n" +
        "{\"suggestions\": [\"建议1\", \"建议2\"], \"focusAreas\": [\"弱项1\", \"弱项2\"], \"recommendedAction\": \"总体建议\"}";

    @Override
    public AnalyticsReportDto getReport(Long userId) {
        AnalyticsReportDto report = new AnalyticsReportDto();

        // 汇总学习记录
        LambdaQueryWrapper<LearningRecord> recordWrapper = new LambdaQueryWrapper<>();
        recordWrapper.eq(LearningRecord::getUserId, userId);
        List<LearningRecord> records = recordMapper.selectList(recordWrapper);

        report.setExerciseCount(records.size());

        int totalSeconds = records.stream().mapToInt(r ->
            r.getTimeSpentSeconds() != null ? r.getTimeSpentSeconds() : 0).sum();
        report.setTotalStudyMinutes(totalSeconds / 60);

        long correctCount = records.stream().filter(r ->
            r.getScore() != null && r.getScore().compareTo(new BigDecimal("60")) >= 0).count();
        report.setCorrectRate(records.isEmpty() ? BigDecimal.ZERO :
            new BigDecimal(correctCount * 100.0 / records.size()).setScale(1, RoundingMode.HALF_UP));

        // 资源学习数量
        LambdaQueryWrapper<Resource> resWrapper = new LambdaQueryWrapper<>();
        resWrapper.eq(Resource::getUserId, userId);
        report.setResourceCount((int) resourceMapper.selectCount(resWrapper).intValue());

        // 各知识点掌握度
        LambdaQueryWrapper<UserProgress> progWrapper = new LambdaQueryWrapper<>();
        progWrapper.eq(UserProgress::getUserId, userId);
        List<UserProgress> progressList = progressMapper.selectList(progWrapper);
        List<Map<String, Object>> masteryList = new ArrayList<>();
        for (UserProgress p : progressList) {
            Map<String, Object> m = new HashMap<>();
            m.put("knowledgePoint", p.getKnowledgePoint());
            m.put("masteryScore", p.getMasteryScore());
            m.put("exerciseCount", p.getExerciseCount());
            m.put("correctCount", p.getCorrectCount());
            masteryList.add(m);
        }
        report.setMasteryByKnowledgePoint(masteryList);
        report.setWeeklyActivity(List.of()); // 简化处理
        return report;
    }

    @Override
    public RadarChartDto getRadarChartData(Long userId) {
        UserProfile profile = userProfileService.getByUserId(userId);

        RadarChartDto radar = new RadarChartDto();
        radar.setLabels(List.of("知识基础", "认知能力", "练习正确率", "学习速度", "兴趣广度", "目标达成"));

        if (profile != null) {
            int kbScore = profile.getKnowledgeBase() != null ? Math.min(100, profile.getKnowledgeBase().length() * 2 + 30) : 30;
            int csScore = scoreFromStyle(profile.getCognitiveStyle());
            int epScore = profile.getErrorPreference() != null ? 50 : 70;
            int lsScore = scoreFromSpeed(profile.getLearningSpeed());
            int idScore = profile.getInterestDirection() != null ? Math.min(100, profile.getInterestDirection().length() * 2 + 30) : 30;
            int goScore = profile.getGoalOrientation() != null ? 60 : 30;

            radar.setScores(List.of(kbScore, csScore, epScore, lsScore, idScore, goScore));
        } else {
            radar.setScores(List.of(30, 30, 50, 30, 30, 30));
        }

        radar.setDetails(List.of());
        return radar;
    }

    @Override
    public AnalyticsSuggestionDto getSuggestion(Long userId) {
        AnalyticsReportDto report = getReport(userId);
        RadarChartDto radar = getRadarChartData(userId);

        String context = String.format(
            "学习数据：总时长%d分钟，资源数%d，练习数%d，正确率%s%%，知识点掌握度%s",
            report.getTotalStudyMinutes(), report.getResourceCount(), report.getExerciseCount(),
            report.getCorrectRate(), report.getMasteryByKnowledgePoint());

        try {
            String response = deepSeekClient.chat(List.of(
                Map.of("role", "system", "content", SUGGESTION_PROMPT),
                Map.of("role", "user", "content", context)
            ), 0.7);

            String json = extractJson(response);
            var parsed = objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});

            AnalyticsSuggestionDto dto = new AnalyticsSuggestionDto();
            @SuppressWarnings("unchecked")
            List<String> suggestions = (List<String>) parsed.getOrDefault("suggestions", List.of());
            @SuppressWarnings("unchecked")
            List<String> focusAreas = (List<String>) parsed.getOrDefault("focusAreas", List.of());
            dto.setSuggestions(suggestions);
            dto.setFocusAreas(focusAreas);
            dto.setRecommendedResourceIds(List.of());
            return dto;
        } catch (Exception e) {
            log.error("AI建议生成失败", e);
            AnalyticsSuggestionDto fallback = new AnalyticsSuggestionDto();
            fallback.setSuggestions(List.of("建议继续按学习路径推进", "重点关注薄弱知识点的练习"));
            fallback.setFocusAreas(List.of("需更多学习数据以精确分析"));
            fallback.setRecommendedResourceIds(List.of());
            return fallback;
        }
    }

    private int scoreFromStyle(String style) {
        if (style == null) return 40;
        if (style.contains("动手") || style.contains("实践")) return 80;
        if (style.contains("视觉")) return 70;
        if (style.contains("文本")) return 65;
        return 50;
    }

    private int scoreFromSpeed(String speed) {
        if (speed == null) return 40;
        if (speed.contains("较快")) return 85;
        if (speed.contains("适中")) return 65;
        if (speed.contains("较慢")) return 40;
        return 50;
    }

    private String extractJson(String raw) {
        String trimmed = raw.trim();
        if (trimmed.startsWith("```")) {
            int start = trimmed.indexOf("\n");
            int end = trimmed.lastIndexOf("```");
            if (start >= 0 && end > start) trimmed = trimmed.substring(start, end).trim();
        }
        int firstBrace = trimmed.indexOf('{');
        int lastBrace = trimmed.lastIndexOf('}');
        if (firstBrace >= 0 && lastBrace > firstBrace)
            return trimmed.substring(firstBrace, lastBrace + 1);
        return trimmed;
    }
}
