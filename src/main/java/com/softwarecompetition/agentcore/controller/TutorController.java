package com.softwarecompetition.agentcore.controller;

import com.softwarecompetition.agentcore.dto.TutorAskRequest;
import com.softwarecompetition.agentcore.dto.TutorAskResponse;
import com.softwarecompetition.agentcore.service.TutorService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Tag(name = "智能辅导", description = "基于RAG检索的智能答疑辅导（加分项）")
@RestController
@RequestMapping("/api/tutor")
public class TutorController {

    private final TutorService tutorService;

    public TutorController(TutorService tutorService) {
        this.tutorService = tutorService;
    }

    @Operation(summary = "提问答疑", description = "基于向量检索知识库的多模态智能答疑")
    @PostMapping(value = "/ask", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<TutorAskResponse> ask(
            @Parameter(description = "用户ID") @RequestHeader("X-User-Id") Long userId,
            @RequestBody TutorAskRequest request) {
        if (request.getQuestion() == null || request.getQuestion().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        TutorAskResponse response = tutorService.ask(userId, request);
        return ResponseEntity.ok(response);
    }
}
