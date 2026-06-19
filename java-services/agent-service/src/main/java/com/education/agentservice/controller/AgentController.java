package com.education.agentservice.controller;

import com.education.agentservice.dto.CoordinationRequest;
import com.education.agentservice.dto.CoordinationResponse;
import com.education.agentservice.dto.ExerciseGenerationRequest;
import com.education.agentservice.dto.GraphQueryRequest;
import com.education.agentservice.dto.LearningPathRequest;
import com.education.agentservice.dto.ResourceGenerationRequest;
import com.education.agentservice.service.AgentFacadeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AgentController {

    private final AgentFacadeService agentFacadeService;

    public AgentController(AgentFacadeService agentFacadeService) {
        this.agentFacadeService = agentFacadeService;
    }

    @GetMapping("/health")
    public java.util.Map<String, String> health() {
        return java.util.Map.of("status", "ok", "service", "agent-service");
    }

    @PostMapping("/agents/coordinate")
    public CoordinationResponse coordinate(@RequestBody CoordinationRequest request) {
        return agentFacadeService.coordinate(request);
    }

    @PostMapping("/resources/generate")
    public java.util.Map<String, Object> generateResource(@RequestBody ResourceGenerationRequest request) {
        return agentFacadeService.generateResource(request);
    }

    @PostMapping("/paths/generate")
    public java.util.Map<String, Object> generatePath(@RequestBody LearningPathRequest request) {
        return agentFacadeService.generatePath(request);
    }

    @PostMapping("/exercises/generate")
    public java.util.Map<String, Object> generateExercises(@RequestBody ExerciseGenerationRequest request) {
        return agentFacadeService.generateExercises(request);
    }

    @PostMapping("/graph/dependencies")
    public java.util.Map<String, Object> getDependencies(@RequestBody GraphQueryRequest request) {
        return agentFacadeService.getDependencies(request);
    }

    @PostMapping("/graph/visualization")
    public java.util.Map<String, Object> getVisualization(@RequestBody GraphQueryRequest request) {
        return agentFacadeService.getVisualization(request);
    }

    @GetMapping("/graph/related-resources/{knowledgePoint}")
    public java.util.Map<String, Object> getRelatedResources(@PathVariable String knowledgePoint) {
        return java.util.Map.of(
            "knowledge_point", knowledgePoint,
            "resources", java.util.List.of(
                java.util.Map.of("name", "示例课件", "type", "courseware", "uri", "/resources/demo")
            )
        );
    }
}
