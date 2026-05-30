package com.softwarecompetition.agentcore.service.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.ChatResponse;
import com.softwarecompetition.agentcore.entity.ProfileConversation;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.service.ProfileAgentService;
import com.softwarecompetition.agentcore.service.ProfileConversationService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class ProfileAgentServiceImpl implements ProfileAgentService {

    private static final Logger log = LoggerFactory.getLogger(ProfileAgentServiceImpl.class);

    private final DeepSeekClient deepSeekClient;
    private final UserProfileService userProfileService;
    private final ProfileConversationService conversationService;
    private final ObjectMapper objectMapper;

    public ProfileAgentServiceImpl(DeepSeekClient deepSeekClient,
                                   UserProfileService userProfileService,
                                   ProfileConversationService conversationService) {
        this.deepSeekClient = deepSeekClient;
        this.userProfileService = userProfileService;
        this.conversationService = conversationService;
        this.objectMapper = new ObjectMapper();
    }

    private static final String SYSTEM_PROMPT =
        "你是一个个性化学习系统中的学生画像构建智能体。" +
        "请自然地与学生对话，同时从对话中提取学习画像信息。\n\n" +
        "需要跟踪的6个画像维度：\n" +
        "- knowledgeBase（知识基础）：学生已经掌握的知识\n" +
        "- cognitiveStyle（认知风格）：学生偏好的学习方式（视觉型、文本型、动手实践型、听觉型）\n" +
        "- errorPreference（易错点偏好）：学生容易出错的知识点或题型\n" +
        "- learningSpeed（学习节奏）：学生的学习速度（较快、适中、较慢）\n" +
        "- interestDirection（兴趣方向）：学生感兴趣的技术方向或领域\n" +
        "- goalOrientation（学习目标）：学生的学习目标（如找工作、考研、兴趣学习等）\n\n" +
        "规则：\n" +
        "1. 友好自然地对话，像一位正在了解学生的导师\n" +
        "2. 当学生透露了某个维度的信息时，提取对应值放入 profileUpdates\n" +
        "3. 只放入本轮确实提到的维度，不要凭空编造\n" +
        "4. 没有新信息时 profileUpdates 为空对象 {}\n" +
        "5. 对话满8轮且大部分维度已获取后，在回复末尾提醒学生\"画像基本完成，可以开始学习了\"\n\n" +
        "你必须严格返回JSON格式，不输出JSON之外的内容。JSON格式：\n" +
        "{\"reply\":\"你的回复\",\"profileUpdates\":{}}";

    @Override
    public ChatResponse chat(Long userId, String message) {
        // 保存用户消息
        conversationService.saveMessage(userId, "user", message);

        // 构建LLM消息列表
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", SYSTEM_PROMPT));

        // 加载最近20条对话历史
        List<ProfileConversation> history = conversationService.getHistoryByUserId(userId, 20);
        for (ProfileConversation conv : history) {
            messages.add(Map.of("role", conv.getRole(), "content", conv.getContent()));
        }

        // 调用DeepSeek
        String responseJson = deepSeekClient.chat(messages, 0.7);

        if (responseJson == null || responseJson.isBlank()) {
            log.warn("DeepSeek返回空内容，userId={}", userId);
            ChatResponse fallback = buildResponse(userId, "抱歉，我暂时无法处理你的消息，请换个方式再说一次。", Map.of());
            conversationService.saveMessage(userId, "assistant", fallback.getReply());
            return fallback;
        }

        // 尝试JSON解析
        String reply;
        Map<String, String> profileUpdates = new HashMap<>();

        String cleanedJson = extractJson(responseJson);
        try {
            Map<String, Object> parsed = objectMapper.readValue(cleanedJson,
                    new TypeReference<>() {});
            reply = (String) parsed.getOrDefault("reply", "");
            @SuppressWarnings("unchecked")
            Map<String, String> updates = (Map<String, String>) parsed.getOrDefault("profileUpdates", new HashMap<>());
            profileUpdates = updates;
        } catch (Exception e) {
            // JSON解析失败，把原始文本当回复
            log.warn("JSON解析失败，启动二次提取: {}", responseJson.substring(0, Math.min(80, responseJson.length())));
            reply = responseJson.trim();

            // 二次提取：将LLM的纯文本回复送入专门的维度提取提示词
            try {
                Map<String, String> extracted = extractDimensionsFromText(reply, userId);
                if (!extracted.isEmpty()) {
                    profileUpdates = extracted;
                    userProfileService.createOrUpdate(userId, extracted);
                    log.info("二次提取成功，维度={}", extracted.keySet());
                }
            } catch (Exception ex) {
                log.warn("二次提取也失败: {}", ex.getMessage());
            }
        }

        // 保存智能体回复
        conversationService.saveMessage(userId, "assistant", reply);

        // 更新画像
        if (!profileUpdates.isEmpty()) {
            userProfileService.createOrUpdate(userId, profileUpdates);
        }

        // 新用户首次对话：自动创建空白画像记录，确保 GET /api/profile 返回200
        if (userProfileService.getByUserId(userId) == null) {
            userProfileService.createOrUpdate(userId, Map.of());
        }

        // 代码层计算完整度（基于数据库实际画像数据，不依赖LLM）
        return buildResponse(userId, reply, profileUpdates);
    }

    private ChatResponse buildResponse(Long userId, String reply, Map<String, String> profileUpdates) {
        ChatResponse response = new ChatResponse();
        response.setReply(reply);
        response.setProfileUpdates(profileUpdates);

        // 从数据库加载当前画像，计算完整度
        UserProfile profile = userProfileService.getByUserId(userId);
        Map<String, String> completeness = new LinkedHashMap<>();
        int filled = 0;

        filled += checkField(completeness, "knowledgeBase", profile != null ? profile.getKnowledgeBase() : null);
        filled += checkField(completeness, "cognitiveStyle", profile != null ? profile.getCognitiveStyle() : null);
        filled += checkField(completeness, "errorPreference", profile != null ? profile.getErrorPreference() : null);
        filled += checkField(completeness, "learningSpeed", profile != null ? profile.getLearningSpeed() : null);
        filled += checkField(completeness, "interestDirection", profile != null ? profile.getInterestDirection() : null);
        filled += checkField(completeness, "goalOrientation", profile != null ? profile.getGoalOrientation() : null);

        response.setProfileCompleteness(completeness);
        // 简单线性：0 → 5, 1-2 → 4, 3-4 → 2, 5 → 1, 6 → 0
        int remaining = switch (filled) {
            case 0 -> 5;
            case 1, 2 -> 4;
            case 3, 4 -> 2;
            case 5 -> 1;
            case 6 -> 0;
            default -> 0;
        };
        response.setEstimatedRemainingRounds(remaining);
        return response;
    }

    private int checkField(Map<String, String> completeness, String key, String value) {
        if (value != null && !value.isBlank()) {
            completeness.put(key, "已获取");
            return 1;
        } else {
            completeness.put(key, "未获取");
            return 0;
        }
    }

    private static final String EXTRACT_PROMPT =
        "你是一个信息提取器。从以下对话文本中提取学生的画像维度信息。" +
        "六个维度：knowledgeBase(知识基础), cognitiveStyle(认知风格), " +
        "errorPreference(易错点), learningSpeed(学习节奏), " +
        "interestDirection(兴趣方向), goalOrientation(学习目标)。" +
        "只输出JSON，不输出其他内容:\n" +
        "{\"knowledgeBase\":\"提取值\",\"cognitiveStyle\":\"提取值\",...}";

    /**
     * 二次提取：当LLM输出纯文本时，再调一次API专门提取维度信息。
     */
    private Map<String, String> extractDimensionsFromText(String text, Long userId) {
        String result = deepSeekClient.chat(
            List.of(
                Map.of("role", "system", "content", EXTRACT_PROMPT),
                Map.of("role", "user", "content", "请从以下文本中提取画像维度：\n" + text)
            ), 0.1);

        try {
            String json = extractJson(result);
            return objectMapper.readValue(json, new TypeReference<Map<String, String>>() {});
        } catch (Exception e) {
            log.warn("二次提取JSON解析失败: {}", e.getMessage());
            return Map.of();
        }
    }

    /**
     * 从LLM响应中提取JSON对象。
     */
    private String extractJson(String raw) {
        String trimmed = raw.trim();
        if (trimmed.startsWith("```")) {
            int start = trimmed.indexOf("\n");
            int end = trimmed.lastIndexOf("```");
            if (start >= 0 && end > start) trimmed = trimmed.substring(start, end).trim();
        }
        if (trimmed.startsWith("{")) return trimmed;
        int firstBrace = trimmed.indexOf('{');
        int lastBrace = trimmed.lastIndexOf('}');
        if (firstBrace >= 0 && lastBrace > firstBrace)
            return trimmed.substring(firstBrace, lastBrace + 1);
        return trimmed;
    }
}
