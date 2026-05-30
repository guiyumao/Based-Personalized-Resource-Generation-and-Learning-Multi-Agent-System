package com.softwarecompetition.agentcore.service;

import com.softwarecompetition.agentcore.entity.KnowledgeBase;

import java.util.List;

public interface EmbeddingService {

    float[] generateEmbedding(String text);

    List<KnowledgeBase> searchSimilar(float[] embedding, int topK);

    void insertKnowledge(String title, String content, String knowledgePoint, String source);
}
