package com.softwarecompetition.agentcore;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@MapperScan("com.softwarecompetition.agentcore.mapper")
@EnableCaching
public class AgentCoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentCoreApplication.class, args);
    }

}
