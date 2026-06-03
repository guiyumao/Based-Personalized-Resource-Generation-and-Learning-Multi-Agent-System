package com.education.common.config;

import com.education.common.security.JwtProperties;
import com.education.common.security.JwtService;
import com.education.common.security.PasswordService;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(JwtProperties.class)
public class CommonConfiguration {

    @Bean
    public JwtService jwtService(JwtProperties jwtProperties) {
        return new JwtService(jwtProperties);
    }

    @Bean
    public PasswordService passwordService() {
        return new PasswordService();
    }
}
