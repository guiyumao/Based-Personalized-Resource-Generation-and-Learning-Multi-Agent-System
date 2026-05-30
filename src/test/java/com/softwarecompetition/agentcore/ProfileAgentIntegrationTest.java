package com.softwarecompetition.agentcore;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.client.DeepSeekClient;
import com.softwarecompetition.agentcore.dto.ChatResponse;
import com.softwarecompetition.agentcore.entity.ProfileConversation;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.mapper.ProfileConversationMapper;
import com.softwarecompetition.agentcore.mapper.UserProfileMapper;
import com.softwarecompetition.agentcore.service.impl.ProfileAgentServiceImpl;
import com.softwarecompetition.agentcore.service.impl.ProfileConversationServiceImpl;
import com.softwarecompetition.agentcore.service.impl.UserProfileServiceImpl;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Import;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;

@SpringBootTest
@Import(TestConfig.class)
class ProfileAgentIntegrationTest {

    @Autowired
    private UserProfileMapper userProfileMapper;

    @Autowired
    private ProfileConversationMapper conversationMapper;

    @Autowired
    private UserProfileServiceImpl userProfileService;

    @Autowired
    private ProfileConversationServiceImpl conversationService;

    @MockBean
    private DeepSeekClient deepSeekClient;

    @Autowired
    private ProfileAgentServiceImpl profileAgentService;

    @Autowired
    private CacheManager cacheManager;

    @BeforeEach
    void setUp() {
        conversationMapper.delete(null);
        userProfileMapper.delete(null);
        // 清除所有缓存，避免缓存污染导致测试间数据残留
        for (String name : cacheManager.getCacheNames()) {
            var cache = cacheManager.getCache(name);
            if (cache != null) cache.clear();
        }
    }

    @Test
    void userProfileService_ShouldCreateAndRetrieveProfile() {
        UserProfile created = userProfileService.createOrUpdate(1L, Map.of(
            "knowledgeBase", "Java基础",
            "cognitiveStyle", "动手实践型",
            "interestDirection", "后端开发"
        ));

        assertNotNull(created.getId());
        assertEquals("Java基础", created.getKnowledgeBase());
        assertEquals("动手实践型", created.getCognitiveStyle());

        UserProfile found = userProfileService.getByUserId(1L);
        assertNotNull(found);
        assertEquals("Java基础", found.getKnowledgeBase());
    }

    @Test
    void userProfileService_ShouldUpdateExistingProfile() {
        userProfileService.createOrUpdate(1L, Map.of("knowledgeBase", "Java基础"));
        userProfileService.createOrUpdate(1L, Map.of("knowledgeBase", "Spring Boot", "learningSpeed", "较快"));

        UserProfile updated = userProfileService.getByUserId(1L);
        assertEquals("Spring Boot", updated.getKnowledgeBase());
        assertEquals("较快", updated.getLearningSpeed());
    }

    @Test
    void conversationService_ShouldSaveAndRetrieveHistory() {
        conversationService.saveMessage(1L, "user", "你好");
        conversationService.saveMessage(1L, "assistant", "你好！有什么可以帮助你的？");
        conversationService.saveMessage(1L, "user", "我想学Java");

        List<ProfileConversation> history = conversationService.getHistoryByUserId(1L, 10);
        assertEquals(3, history.size());
        assertEquals("user", history.get(0).getRole());
        assertEquals("assistant", history.get(1).getRole());
        assertEquals("user", history.get(2).getRole());
    }

    @Test
    void profileAgentService_ShouldChatAndUpdateProfile() throws Exception {
        String mockResponse = "{\"reply\": \"你好！了解了，你有Java基础，喜欢动手实践。\", " +
            "\"profileUpdates\": {\"knowledgeBase\": \"Java基础\", \"cognitiveStyle\": \"动手实践型\"}}";

        when(deepSeekClient.chat(anyList(), anyDouble())).thenReturn(mockResponse);

        ChatResponse response = profileAgentService.chat(1L, "我学过Java基础，喜欢通过做项目来学习");

        assertNotNull(response.getReply());
        assertEquals("Java基础", response.getProfileUpdates().get("knowledgeBase"));
        assertEquals("动手实践型", response.getProfileUpdates().get("cognitiveStyle"));

        // Verify conversation history stored
        List<ProfileConversation> history = conversationService.getHistoryByUserId(1L, 10);
        assertEquals(2, history.size()); // user + assistant
        assertEquals("user", history.get(0).getRole());
        assertEquals("assistant", history.get(1).getRole());

        // Verify profile updated
        UserProfile profile = userProfileService.getByUserId(1L);
        assertNotNull(profile);
        assertEquals("Java基础", profile.getKnowledgeBase());
        assertEquals("动手实践型", profile.getCognitiveStyle());
    }

    @Test
    void profileAgentService_ShouldHandleEmptyProfileUpdates() throws Exception {
        String mockResponse = "{\"reply\": \"今天想聊什么？\", \"profileUpdates\": {}}";

        when(deepSeekClient.chat(anyList(), anyDouble())).thenReturn(mockResponse);

        ChatResponse response = profileAgentService.chat(1L, "今天天气不错");

        assertNotNull(response.getReply());
        assertTrue(response.getProfileUpdates().isEmpty());

        // 新用户即使没有维度提取，也会创建空白画像记录
        UserProfile profile = userProfileService.getByUserId(1L);
        assertNotNull(profile);
        assertNull(profile.getKnowledgeBase());
    }
}
