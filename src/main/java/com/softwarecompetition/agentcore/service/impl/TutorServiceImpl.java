package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.TutorAskRequest;
import com.softwarecompetition.agentcore.dto.TutorAskResponse;
import com.softwarecompetition.agentcore.entity.KnowledgeBase;
import com.softwarecompetition.agentcore.mapper.KnowledgeBaseMapper;
import com.softwarecompetition.agentcore.service.TutorService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class TutorServiceImpl implements TutorService {

    private static final Logger log = LoggerFactory.getLogger(TutorServiceImpl.class);

    private final DeepSeekClient deepSeekClient;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    public TutorServiceImpl(DeepSeekClient deepSeekClient,
                            KnowledgeBaseMapper knowledgeBaseMapper) {
        this.deepSeekClient = deepSeekClient;
        this.knowledgeBaseMapper = knowledgeBaseMapper;
    }

    private static final String TUTOR_PROMPT =
        "你是一个智能学习辅导教师。请根据提供的知识库内容和学生的提问，给出详细、准确、易懂的解答。\n" +
        "规则：\n" +
        "1. 优先基于知识库内容回答，无法从知识库找到的信息可结合你的知识补充\n" +
        "2. 解答要结构化：概念解释 → 核心要点 → 举例说明 → 常见误区 → 延伸思考\n" +
        "3. 根据学生的知识水平调整语言难度\n" +
        "4. 如果问题涉及代码，提供可运行的示例\n" +
        "5. 如果信息不确定，明确指出并建议查阅资料";

    @Override
    public TutorAskResponse ask(Long userId, TutorAskRequest request) {
        // 关键词检索知识库（毫秒级，无需embedding调用）
        List<KnowledgeBase> results = searchByKeywords(request.getQuestion(), 3);
        List<String> contextSnippets = new ArrayList<>();
        double confidence = results.isEmpty() ? 0.5 : 0.8;

        for (KnowledgeBase kb : results) {
            String snippet = kb.getContent() != null && kb.getContent().length() > 300
                ? kb.getContent().substring(0, 300) + "..."
                : kb.getContent();
            contextSnippets.add(kb.getTitle() + ": " + snippet);
        }

        // 构建带知识库上下文的prompt
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", TUTOR_PROMPT));

        if (!contextSnippets.isEmpty()) {
            String contextStr = "【知识库参考资料】\n" + String.join("\n---\n", contextSnippets);
            messages.add(Map.of("role", "system", "content", contextStr));
        }

        messages.add(Map.of("role", "user", "content", request.getQuestion()));

        // 仅一次LLM调用
        String answer = deepSeekClient.chat(messages, 0.5);

        TutorAskResponse response = new TutorAskResponse();
        response.setAnswer(answer);
        response.setContextSnippets(contextSnippets);
        response.setConfidence(confidence);
        return response;
    }

    /**
     * 基于关键词的知识库检索，毫秒级完成，无需embedding API调用。
     * 优先级：精确标题匹配 > 知识点匹配 > 内容包含关键词。
     */
    private List<KnowledgeBase> searchByKeywords(String question, int topK) {
        List<KnowledgeBase> results = new ArrayList<>();

        // 提取问题中的关键词（简单分词）
        Set<String> keywords = extractKeywords(question);
        if (keywords.isEmpty()) return results;

        // 查全量知识库（数据量小时全量查，实际生产可加缓存）
        List<KnowledgeBase> all = knowledgeBaseMapper.selectList(null);
        if (all.isEmpty()) return results;

        // 相关度评分排序
        List<Map.Entry<KnowledgeBase, Integer>> scored = new ArrayList<>();
        for (KnowledgeBase kb : all) {
            int score = 0;
            String title = kb.getTitle() != null ? kb.getTitle().toLowerCase() : "";
            String content = kb.getContent() != null ? kb.getContent().toLowerCase() : "";
            String kp = kb.getKnowledgePoint() != null ? kb.getKnowledgePoint().toLowerCase() : "";

            for (String kw : keywords) {
                if (title.equals(kw)) score += 10;       // 标题完全匹配
                else if (title.contains(kw)) score += 5;  // 标题包含
                if (kp.contains(kw)) score += 3;          // 知识点匹配
                if (content.contains(kw)) score += 2;     // 内容包含
            }
            if (score > 0) scored.add(new AbstractMap.SimpleEntry<>(kb, score));
        }

        scored.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));

        for (int i = 0; i < Math.min(topK, scored.size()); i++) {
            results.add(scored.get(i).getKey());
        }
        return results;
    }

    private Set<String> extractKeywords(String question) {
        // 简单分词：按中英文标点和空格拆分，取长度>=2的词
        Set<String> keywords = new LinkedHashSet<>();
        for (String token : question.split("[\\s，。！？,!.?；;：:、（）()]+")) {
            token = token.trim().toLowerCase();
            if (token.length() >= 2) keywords.add(token);
        }
        return keywords;
    }
}
