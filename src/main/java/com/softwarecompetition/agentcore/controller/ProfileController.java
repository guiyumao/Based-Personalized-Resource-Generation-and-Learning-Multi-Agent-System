package com.softwarecompetition.agentcore.controller;

import com.softwarecompetition.agentcore.dto.ChatRequest;
import com.softwarecompetition.agentcore.dto.ChatResponse;
import com.softwarecompetition.agentcore.dto.ProfileDto;
import com.softwarecompetition.agentcore.entity.UserProfile;
import com.softwarecompetition.agentcore.service.ProfileAgentService;
import com.softwarecompetition.agentcore.service.UserProfileService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Tag(name = "用户画像", description = "画像构建智能体对话、画像查询与更新")
@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final ProfileAgentService profileAgentService;
    private final UserProfileService userProfileService;

    public ProfileController(ProfileAgentService profileAgentService,
                             UserProfileService userProfileService) {
        this.profileAgentService = profileAgentService;
        this.userProfileService = userProfileService;
    }

    @Operation(summary = "画像构建对话", description = "发送对话消息给画像构建智能体，智能体自然回复并自动从对话中提取六维度画像信息")
    @PostMapping(value = "/chat", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ChatResponse> chat(@RequestBody ChatRequest request) {
        if (request.getUserId() == null || request.getMessage() == null || request.getMessage().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        ChatResponse response = profileAgentService.chat(request.getUserId(), request.getMessage());
        return ResponseEntity.ok(response);
    }

    @Operation(summary = "获取用户画像", description = "获取当前用户的完整六维度画像数据")
    @GetMapping
    public ResponseEntity<ProfileDto> getProfile(
            @Parameter(description = "用户ID（当前明文传递，后续切换JWT）", required = true)
            @RequestHeader("X-User-Id") Long userId) {
        UserProfile profile = userProfileService.getByUserId(userId);
        if (profile == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(toDto(profile));
    }

    @Operation(summary = "手动更新画像", description = "手动更新用户画像的指定维度")
    @PutMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProfileDto> updateProfile(
            @Parameter(description = "用户ID（当前明文传递，后续切换JWT）", required = true)
            @RequestHeader("X-User-Id") Long userId,
            @RequestBody Map<String, String> updates) {
        if (updates.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        UserProfile profile = userProfileService.createOrUpdate(userId, updates);
        return ResponseEntity.ok(toDto(profile));
    }

    private ProfileDto toDto(UserProfile profile) {
        ProfileDto dto = new ProfileDto();
        dto.setUserId(profile.getUserId());
        dto.setKnowledgeBase(profile.getKnowledgeBase());
        dto.setCognitiveStyle(profile.getCognitiveStyle());
        dto.setErrorPreference(profile.getErrorPreference());
        dto.setLearningSpeed(profile.getLearningSpeed());
        dto.setInterestDirection(profile.getInterestDirection());
        dto.setGoalOrientation(profile.getGoalOrientation());
        dto.setCreatedAt(profile.getCreatedAt());
        dto.setUpdatedAt(profile.getUpdatedAt());
        return dto;
    }
}
