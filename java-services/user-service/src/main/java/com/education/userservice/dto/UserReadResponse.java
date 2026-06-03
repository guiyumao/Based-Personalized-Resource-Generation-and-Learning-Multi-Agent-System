package com.education.userservice.dto;

import com.education.userservice.model.UserRole;

public record UserReadResponse(
    Long id,
    String username,
    UserRole role,
    String email
) {
}
