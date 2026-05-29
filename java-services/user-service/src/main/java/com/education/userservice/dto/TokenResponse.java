package com.education.userservice.dto;

import com.education.userservice.model.UserRole;

public record TokenResponse(
    String access_token,
    String token_type,
    Long user_id,
    String username,
    UserRole role
) {
}
