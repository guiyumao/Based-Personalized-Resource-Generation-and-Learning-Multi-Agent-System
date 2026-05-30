package com.softwarecompetition.agentcore;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.softwarecompetition.agentcore.dto.ChatRequest;
import com.softwarecompetition.agentcore.dto.ChatResponse;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.service.ProfileAgentService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.Map;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestConfig.class)
class ProfileControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ProfileAgentService profileAgentService;

    @MockBean
    private UserProfileService userProfileService;

    @Test
    void chat_ShouldReturnAgentResponse() throws Exception {
        ChatRequest request = new ChatRequest();
        request.setUserId(1L);
        request.setMessage("你好，我在学习Java");

        ChatResponse mockResponse = new ChatResponse();
        mockResponse.setReply("你好！Java是很好的入门语言，能告诉我你目前的基础吗？");
        mockResponse.setProfileUpdates(Map.of("interestDirection", "Java"));

        when(profileAgentService.chat(anyLong(), anyString())).thenReturn(mockResponse);

        mockMvc.perform(post("/api/profile/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("你好！Java是很好的入门语言，能告诉我你目前的基础吗？"))
                .andExpect(jsonPath("$.profileUpdates.interestDirection").value("Java"));
    }

    @Test
    void chat_ShouldReturnBadRequest_WhenUserIdMissing() throws Exception {
        ChatRequest request = new ChatRequest();
        request.setMessage("Hello");

        mockMvc.perform(post("/api/profile/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void chat_ShouldReturnBadRequest_WhenMessageBlank() throws Exception {
        ChatRequest request = new ChatRequest();
        request.setUserId(1L);
        request.setMessage("   ");

        mockMvc.perform(post("/api/profile/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getProfile_ShouldReturnProfile() throws Exception {
        UserProfile profile = new UserProfile();
        profile.setUserId(1L);
        profile.setKnowledgeBase("Java基础");
        profile.setCognitiveStyle("动手实践型");
        profile.setInterestDirection("后端开发");
        profile.setCreatedAt(LocalDateTime.now());
        profile.setUpdatedAt(LocalDateTime.now());

        when(userProfileService.getByUserId(1L)).thenReturn(profile);

        mockMvc.perform(get("/api/profile")
                        .header("X-User-Id", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(1))
                .andExpect(jsonPath("$.knowledgeBase").value("Java基础"))
                .andExpect(jsonPath("$.cognitiveStyle").value("动手实践型"));
    }

    @Test
    void getProfile_ShouldReturn404_WhenProfileNotFound() throws Exception {
        when(userProfileService.getByUserId(999L)).thenReturn(null);

        mockMvc.perform(get("/api/profile")
                        .header("X-User-Id", "999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void updateProfile_ShouldReturnUpdatedProfile() throws Exception {
        Map<String, String> updates = Map.of("knowledgeBase", "Spring Boot");

        UserProfile updated = new UserProfile();
        updated.setUserId(1L);
        updated.setKnowledgeBase("Spring Boot");

        when(userProfileService.createOrUpdate(anyLong(), any())).thenReturn(updated);

        mockMvc.perform(put("/api/profile")
                        .header("X-User-Id", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(updates)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.knowledgeBase").value("Spring Boot"));
    }

    @Test
    void updateProfile_ShouldReturnBadRequest_WhenBodyEmpty() throws Exception {
        mockMvc.perform(put("/api/profile")
                        .header("X-User-Id", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }
}
