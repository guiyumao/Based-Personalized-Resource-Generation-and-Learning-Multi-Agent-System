package com.education.userservice.model;

import java.util.List;
import java.util.Map;

public class UserProfileEntity {

    private Long userId;
    private Map<String, Integer> masteryJson;
    private String learningStyle;
    private Map<String, Integer> cognitiveAbilities;
    private Map<String, Object> habits;

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public Map<String, Integer> getMasteryJson() {
        return masteryJson;
    }

    public void setMasteryJson(Map<String, Integer> masteryJson) {
        this.masteryJson = masteryJson;
    }

    public String getLearningStyle() {
        return learningStyle;
    }

    public void setLearningStyle(String learningStyle) {
        this.learningStyle = learningStyle;
    }

    public Map<String, Integer> getCognitiveAbilities() {
        return cognitiveAbilities;
    }

    public void setCognitiveAbilities(Map<String, Integer> cognitiveAbilities) {
        this.cognitiveAbilities = cognitiveAbilities;
    }

    public Map<String, Object> getHabits() {
        return habits;
    }

    public void setHabits(Map<String, Object> habits) {
        this.habits = habits;
    }
}
