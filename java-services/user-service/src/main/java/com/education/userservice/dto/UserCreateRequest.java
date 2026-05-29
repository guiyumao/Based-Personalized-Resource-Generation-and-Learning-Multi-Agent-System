package com.education.userservice.dto;

import com.education.userservice.model.UserRole;
import jakarta.validation.constraints.NotBlank;

public record UserCreateRequest(
    @NotBlank String username,
    @NotBlank String password,
    UserRole role,
    String email
) {
}
