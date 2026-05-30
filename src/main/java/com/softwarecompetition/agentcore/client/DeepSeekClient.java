package com.softwarecompetition.agentcore.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

@Component
public class DeepSeekClient {

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    @Value("${llm.deepseek.api-key}")
    private String apiKey;

    @Value("${llm.deepseek.url}")
    private String apiUrl;

    @Value("${llm.deepseek.model}")
    private String model;

    @Value("${agent.embedding.dimension:1536}")
    private int embeddingDimension;

    public DeepSeekClient() {
        this.restTemplate = new RestTemplate();
        this.objectMapper = new ObjectMapper();
    }

    public String chat(List<Map<String, String>> messages, double temperature) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(apiKey);

        Map<String, Object> body = Map.of(
            "model", model,
            "messages", messages,
            "temperature", temperature
        );

        HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);

        try {
            ResponseEntity<String> response = restTemplate.postForEntity(apiUrl, request, String.class);
            JsonNode root = objectMapper.readTree(response.getBody());
            return root.path("choices").get(0).path("message").path("content").asText();
        } catch (Exception e) {
            throw new RuntimeException("DeepSeek API调用失败: " + e.getMessage(), e);
        }
    }

    /**
     * 通过DeepSeek Chat API生成文本的语义向量。
     * 由于DeepSeek暂无独立Embedding API，通过特殊prompt让模型输出向量表示。
     */
    public float[] embed(String text) {
        String prompt = "请将以下文本转换为语义向量表示。返回一个包含" + embeddingDimension
            + "个浮点数的JSON数组，每个值在-1到1之间，表示文本在对应维度的语义特征。只返回JSON数组，不要任何解释。\n\n文本：" + text;

        List<Map<String, String>> messages = List.of(
            Map.of("role", "system", "content", "你是一个文本向量化工具。你只返回JSON数组，不返回任何其他内容。"),
            Map.of("role", "user", "content", prompt)
        );

        String response = chat(messages, 0.1);
        return parseEmbeddingArray(response);
    }

    private float[] parseEmbeddingArray(String response) {
        try {
            // 清理可能的markdown包裹
            String cleaned = response.trim();
            if (cleaned.startsWith("```")) {
                int start = cleaned.indexOf("[");
                int end = cleaned.lastIndexOf("]");
                if (start >= 0 && end > start) {
                    cleaned = cleaned.substring(start, end + 1);
                }
            }
            JsonNode array = objectMapper.readTree(cleaned);
            float[] embedding = new float[array.size()];
            for (int i = 0; i < array.size(); i++) {
                embedding[i] = (float) array.get(i).asDouble();
            }
            return embedding;
        } catch (Exception e) {
            throw new RuntimeException("解析embedding向量失败: " + e.getMessage(), e);
        }
    }
}
