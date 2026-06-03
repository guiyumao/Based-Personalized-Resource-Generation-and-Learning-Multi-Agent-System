package com.education.userservice.dto;

import com.education.userservice.model.UserRole;
import jakarta.validation.constraints.NotBlank;

public record UserRegisterRequest(
    @NotBlank String username,
    @NotBlank String password,
    UserRole role,
    String email
) {
}
