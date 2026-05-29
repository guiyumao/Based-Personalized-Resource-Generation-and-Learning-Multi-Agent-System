package com.education.userservice.dto;

import java.util.Map;

public record UserProfileReadResponse(
    Long userId,
    Map<String, Integer> masteryJson,
    String learningStyle,
    Map<String, Integer> cognitiveAbilities,
    Map<String, Object> habits
) {
}
