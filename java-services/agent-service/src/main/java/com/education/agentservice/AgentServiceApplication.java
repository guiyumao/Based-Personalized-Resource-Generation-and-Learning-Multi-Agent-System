package com.education.agentservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.education")
public class AgentServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentServiceApplication.class, args);
    }
}
