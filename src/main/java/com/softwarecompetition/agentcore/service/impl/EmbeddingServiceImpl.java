package com.softwarecompetition.agentcore.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.entity.KnowledgeBase;
import com.softwarecompetition.agentcore.mapper.KnowledgeBaseMapper;
import com.softwarecompetition.agentcore.service.EmbeddingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class EmbeddingServiceImpl implements EmbeddingService {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingServiceImpl.class);

    private final DeepSeekClient deepSeekClient;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final ObjectMapper objectMapper;

    @Value("${agent.embedding.top-k:5}")
    private int defaultTopK;

    public EmbeddingServiceImpl(DeepSeekClient deepSeekClient,
                                KnowledgeBaseMapper knowledgeBaseMapper) {
        this.deepSeekClient = deepSeekClient;
        this.knowledgeBaseMapper = knowledgeBaseMapper;
        this.objectMapper = new ObjectMapper();
    }

    @Override
    public float[] generateEmbedding(String text) {
        return deepSeekClient.embed(text);
    }

    @Override
    public List<KnowledgeBase> searchSimilar(float[] queryEmbedding, int topK) {
        int k = topK > 0 ? topK : defaultTopK;

        // 查出所有有embedding的知识库条目
        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();
        wrapper.isNotNull(KnowledgeBase::getEmbedding);
        List<KnowledgeBase> all = knowledgeBaseMapper.selectList(wrapper);

        if (all.isEmpty()) {
            return List.of();
        }

        // 在Java层计算余弦相似度并排序
        List<Map.Entry<KnowledgeBase, Double>> scored = new ArrayList<>();
        for (KnowledgeBase kb : all) {
            float[] kbEmbedding = parseEmbedding(kb.getEmbedding());
            if (kbEmbedding != null && kbEmbedding.length == queryEmbedding.length) {
                double similarity = cosineSimilarity(queryEmbedding, kbEmbedding);
                scored.add(new AbstractMap.SimpleEntry<>(kb, similarity));
            }
        }

        scored.sort((a, b) -> Double.compare(b.getValue(), a.getValue()));

        List<KnowledgeBase> result = new ArrayList<>();
        for (int i = 0; i < Math.min(k, scored.size()); i++) {
            result.add(scored.get(i).getKey());
        }
        return result;
    }

    @Override
    public void insertKnowledge(String title, String content, String knowledgePoint, String source) {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setTitle(title);
        kb.setContent(content);
        kb.setKnowledgePoint(knowledgePoint);
        kb.setSource(source);
        kb.setContentType("text");

        try {
            float[] embedding = generateEmbedding(content);
            kb.setEmbedding(arrayToJson(embedding));
        } catch (Exception e) {
            log.warn("生成embedding失败，正文存储: {}", e.getMessage());
        }

        knowledgeBaseMapper.insert(kb);
        log.info("知识库条目入库成功: {}", title);
    }

    private String arrayToJson(float[] array) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < array.length; i++) {
            if (i > 0) sb.append(",");
            sb.append(String.format("%.8f", array[i]));
        }
        sb.append("]");
        return sb.toString();
    }

    private float[] parseEmbedding(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            List<Double> list = objectMapper.readValue(json, new TypeReference<List<Double>>() {});
            float[] result = new float[list.size()];
            for (int i = 0; i < list.size(); i++) {
                result[i] = list.get(i).floatValue();
            }
            return result;
        } catch (Exception e) {
            log.warn("解析embedding失败: {}", e.getMessage());
            return null;
        }
    }

    private double cosineSimilarity(float[] a, float[] b) {
        double dot = 0, normA = 0, normB = 0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            normA += (double) a[i] * a[i];
            normB += (double) b[i] * b[i];
        }
        if (normA == 0 || normB == 0) return 0;
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }
}
