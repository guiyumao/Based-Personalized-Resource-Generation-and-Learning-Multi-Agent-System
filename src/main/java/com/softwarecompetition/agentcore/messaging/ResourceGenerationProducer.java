package com.softwarecompetition.agentcore.messaging;

import com.softwarecompetition.agentcore.config.RabbitMQConfig;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class ResourceGenerationProducer {

    private final RabbitTemplate rabbitTemplate;

    public ResourceGenerationProducer(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void send(ResourceGenerationMessage message) {
        rabbitTemplate.convertAndSend(
                RabbitMQConfig.EXCHANGE,
                RabbitMQConfig.RESOURCE_GENERATE_ROUTING_KEY,
                message);
    }
}
