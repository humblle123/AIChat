package com.yao.yao_agent.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/health")
public class HealthController {

    @Value("${spring.application.name:yuaiagent}")
    private String appName;

    @Value("${spring.application.version:unknown}")
    private String appVersion;

    private final LocalDateTime startTime = LocalDateTime.now();

    @GetMapping
    public Map<String, Object> healthCheck() {
        Map<String, Object> healthInfo = new HashMap<>();
        healthInfo.put("status", "ok");
        healthInfo.put("appName", appName);
        healthInfo.put("appVersion", appVersion);
        healthInfo.put("startTime", startTime.toString());
        healthInfo.put("currentTime", LocalDateTime.now().toString());
        return healthInfo;
    }
}