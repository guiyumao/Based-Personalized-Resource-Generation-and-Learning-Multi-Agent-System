package com.softwarecompetition.agentcore.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Knife4jConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("AgentCore - 个性化学习智能体系统")
                        .description("多智能体协同学习平台：画像构建、资源生成、学习路径、智能辅导、学习分析")
                        .version("1.1.0"));
    }
}
