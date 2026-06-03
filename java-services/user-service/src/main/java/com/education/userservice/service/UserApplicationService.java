package com.education.userservice.service;

import com.education.common.security.JwtService;
import com.education.common.security.PasswordService;
import com.education.userservice.dto.LearnerProfileDashboardResponse;
import com.education.userservice.dto.TokenResponse;
import com.education.userservice.dto.UserCreateRequest;
import com.education.userservice.dto.UserLoginRequest;
import com.education.userservice.dto.UserProfileReadResponse;
import com.education.userservice.dto.UserReadResponse;
import com.education.userservice.dto.UserRegisterRequest;
import com.education.userservice.model.UserEntity;
import com.education.userservice.model.UserProfileEntity;
import com.education.userservice.model.UserRole;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class UserApplicationService {

    private final AtomicLong idSequence = new AtomicLong(1);
    private final Map<Long, UserEntity> users = new ConcurrentHashMap<>();
    private final Map<Long, UserProfileEntity> profiles = new ConcurrentHashMap<>();
    private final PasswordService passwordService;
    private final JwtService jwtService;

    public UserApplicationService(PasswordService passwordService, JwtService jwtService) {
        this.passwordService = passwordService;
        this.jwtService = jwtService;
    }

    public UserReadResponse createUser(UserCreateRequest request) {
        ensureUsernameAvailable(request.username());
        UserEntity user = buildUser(request.username(), request.password(), request.role(), request.email());
        saveUser(user);
        return toUserRead(user);
    }

    public TokenResponse register(UserRegisterRequest request) {
        ensureUsernameAvailable(request.username());
        UserEntity user = buildUser(request.username(), request.password(), request.role(), request.email());
        saveUser(user);
        return buildToken(user);
    }

    public TokenResponse login(UserLoginRequest request) {
        UserEntity user = users.values().stream()
            .filter(item -> item.getUsername().equals(request.username()))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Invalid username or password."));
        if (!passwordService.matches(request.password(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Invalid username or password.");
        }
        return buildToken(user);
    }

    public UserReadResponse getUser(Long userId) {
        return toUserRead(getUserEntity(userId));
    }

    public UserReadResponse getCurrentUser(String bearerToken) {
        String subject = jwtService.parseSubject(stripBearer(bearerToken));
        return getUser(Long.parseLong(subject));
    }

    public UserProfileReadResponse getProfile(Long userId) {
        UserProfileEntity profile = profiles.get(userId);
        if (profile == null) {
            throw new IllegalArgumentException("Profile not found.");
        }
        return new UserProfileReadResponse(
            profile.getUserId(),
            profile.getMasteryJson(),
            profile.getLearningStyle(),
            profile.getCognitiveAbilities(),
            profile.getHabits()
        );
    }

    public LearnerProfileDashboardResponse getDashboard(Long userId) {
        getUserEntity(userId);
        return new LearnerProfileDashboardResponse(
            userId,
            "视觉型 + 练习驱动",
            68,
            210,
            "最近主要在晚间学习，建议先看课件再做课后自测。",
            List.of(
                new LearnerProfileDashboardResponse.MetricItem("知识掌握", 68),
                new LearnerProfileDashboardResponse.MetricItem("逻辑分析", 72),
                new LearnerProfileDashboardResponse.MetricItem("作答稳定性", 64),
                new LearnerProfileDashboardResponse.MetricItem("完成速度", 60),
                new LearnerProfileDashboardResponse.MetricItem("复盘反思", 75)
            ),
            List.of(
                new LearnerProfileDashboardResponse.HeatmapItem("Python 循环", 68),
                new LearnerProfileDashboardResponse.HeatmapItem("条件判断", 63),
                new LearnerProfileDashboardResponse.HeatmapItem("列表与字典", 74),
                new LearnerProfileDashboardResponse.HeatmapItem("函数封装", 58),
                new LearnerProfileDashboardResponse.HeatmapItem("综合应用", 52)
            )
        );
    }

    public Map<String, String> issueToken(Long userId) {
        UserEntity user = getUserEntity(userId);
        return Map.of(
            "access_token", jwtService.createToken(String.valueOf(user.getId())),
            "token_type", "bearer"
        );
    }

    private void saveUser(UserEntity user) {
        users.put(user.getId(), user);

        UserProfileEntity profile = new UserProfileEntity();
        profile.setUserId(user.getId());
        profile.setMasteryJson(new ConcurrentHashMap<>());
        profile.setLearningStyle("VARK");
        profile.setCognitiveAbilities(new ConcurrentHashMap<>());
        profile.setHabits(new ConcurrentHashMap<>());
        profiles.put(user.getId(), profile);
    }

    private UserEntity buildUser(String username, String password, UserRole role, String email) {
        UserEntity user = new UserEntity();
        user.setId(idSequence.getAndIncrement());
        user.setUsername(username);
        user.setPasswordHash(passwordService.hash(password));
        user.setRole(role == null ? UserRole.student : role);
        user.setEmail(email);
        user.setCreatedAt(Instant.now());
        return user;
    }

    private UserEntity getUserEntity(Long userId) {
        UserEntity user = users.get(userId);
        if (user == null) {
            throw new IllegalArgumentException("User not found.");
        }
        return user;
    }

    private TokenResponse buildToken(UserEntity user) {
        return new TokenResponse(
            jwtService.createToken(String.valueOf(user.getId())),
            "bearer",
            user.getId(),
            user.getUsername(),
            user.getRole()
        );
    }

    private UserReadResponse toUserRead(UserEntity user) {
        return new UserReadResponse(user.getId(), user.getUsername(), user.getRole(), user.getEmail());
    }

    private void ensureUsernameAvailable(String username) {
        boolean exists = users.values().stream().anyMatch(item -> item.getUsername().equals(username));
        if (exists) {
            throw new IllegalArgumentException("Username already exists.");
        }
    }

    private String stripBearer(String bearerToken) {
        if (bearerToken == null || bearerToken.isBlank()) {
            throw new IllegalArgumentException("Missing Authorization header.");
        }
        return bearerToken.replace("Bearer ", "").trim();
    }
}
