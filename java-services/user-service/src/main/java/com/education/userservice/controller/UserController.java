package com.education.userservice.controller;

import com.education.common.api.ApiResponse;
import com.education.userservice.dto.LearnerProfileDashboardResponse;
import com.education.userservice.dto.TokenResponse;
import com.education.userservice.dto.UserCreateRequest;
import com.education.userservice.dto.UserLoginRequest;
import com.education.userservice.dto.UserProfileReadResponse;
import com.education.userservice.dto.UserReadResponse;
import com.education.userservice.dto.UserRegisterRequest;
import com.education.userservice.service.UserApplicationService;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
public class UserController {

    private final UserApplicationService userApplicationService;

    public UserController(UserApplicationService userApplicationService) {
        this.userApplicationService = userApplicationService;
    }

    @PostMapping
    public UserReadResponse createUser(@Valid @RequestBody UserCreateRequest request) {
        return userApplicationService.createUser(request);
    }

    @PostMapping("/register")
    public TokenResponse register(@Valid @RequestBody UserRegisterRequest request) {
        return userApplicationService.register(request);
    }

    @PostMapping("/login")
    public TokenResponse login(@Valid @RequestBody UserLoginRequest request) {
        return userApplicationService.login(request);
    }

    @GetMapping("/me")
    public UserReadResponse getMe(@RequestHeader("Authorization") String authorization) {
        return userApplicationService.getCurrentUser(authorization);
    }

    @GetMapping("/{userId}")
    public UserReadResponse getUser(@PathVariable Long userId) {
        return userApplicationService.getUser(userId);
    }

    @GetMapping("/{userId}/profile")
    public UserProfileReadResponse getProfile(@PathVariable Long userId) {
        return userApplicationService.getProfile(userId);
    }

    @GetMapping("/{userId}/profile/dashboard")
    public LearnerProfileDashboardResponse getProfileDashboard(@PathVariable Long userId) {
        return userApplicationService.getDashboard(userId);
    }

    @PostMapping("/{userId}/token")
    public Map<String, String> createToken(@PathVariable Long userId) {
        return userApplicationService.issueToken(userId);
    }
}
