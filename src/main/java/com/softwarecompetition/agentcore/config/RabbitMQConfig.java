package com.softwarecompetition.agentcore.config;

import org.springframework.amqp.core.*;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "spring.rabbitmq.host")
public class RabbitMQConfig {

    public static final String EXCHANGE = "agent.exchange";
    public static final String RESOURCE_GENERATE_QUEUE = "resource.generate.queue";
    public static final String RESOURCE_GENERATE_DLQ = "resource.generate.dlq";
    public static final String RESOURCE_GENERATE_ROUTING_KEY = "resource.generate";

    @Bean
    public DirectExchange agentExchange() {
        return new DirectExchange(EXCHANGE);
    }

    // 死信队列
    @Bean
    public Queue resourceGenerateDlq() {
        return new Queue(RESOURCE_GENERATE_DLQ, true);
    }

    @Bean
    public Binding dlqBinding() {
        return BindingBuilder.bind(resourceGenerateDlq()).to(agentExchange()).with(RESOURCE_GENERATE_DLQ);
    }

    // 资源生成队列（绑定死信）
    @Bean
    public Queue resourceGenerateQueue() {
        return QueueBuilder.durable(RESOURCE_GENERATE_QUEUE)
                .withArgument("x-dead-letter-exchange", EXCHANGE)
                .withArgument("x-dead-letter-routing-key", RESOURCE_GENERATE_DLQ)
                .build();
    }

    @Bean
    public Binding resourceGenerateBinding() {
        return BindingBuilder.bind(resourceGenerateQueue()).to(agentExchange()).with(RESOURCE_GENERATE_ROUTING_KEY);
    }

    @Bean
    public Jackson2JsonMessageConverter messageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
