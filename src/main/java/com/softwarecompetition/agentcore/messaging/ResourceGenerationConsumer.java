package com.softwarecompetition.agentcore.messaging;

import com.rabbitmq.client.Channel;
import com.softwarecompetition.agentcore.config.RabbitMQConfig;
import com.softwarecompetition.agentcore.dto.ResourceGenerateRequest;
import com.softwarecompetition.agentcore.service.ResourceCoordinationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

import java.io.IOException;

@Component
public class ResourceGenerationConsumer {

    private static final Logger log = LoggerFactory.getLogger(ResourceGenerationConsumer.class);

    private final ResourceCoordinationService coordinationService;

    public ResourceGenerationConsumer(ResourceCoordinationService coordinationService) {
        this.coordinationService = coordinationService;
    }

    @RabbitListener(queues = RabbitMQConfig.RESOURCE_GENERATE_QUEUE, ackMode = "MANUAL")
    public void onMessage(ResourceGenerationMessage message, Channel channel,
                          @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag) {
        log.info("收到资源生成任务: taskId={}, userId={}", message.getTaskId(), message.getUserId());
        try {
            ResourceGenerateRequest request = new ResourceGenerateRequest();
            request.setRequestText(message.getRequestText());
            request.setResourceType(message.getResourceType());
            request.setKnowledgePoint(message.getKnowledgePoint());

            coordinationService.executeGeneration(message.getTaskId(), message.getUserId(), request);

            channel.basicAck(deliveryTag, false);
            log.info("资源生成任务完成: taskId={}", message.getTaskId());
        } catch (Exception e) {
            log.error("资源生成任务失败: taskId={}", message.getTaskId(), e);
            try {
                // 拒绝并重新入队（最多重试3次，由spring.rabbitmq配置控制）
                channel.basicNack(deliveryTag, false, true);
            } catch (IOException ex) {
                log.error("消息确认失败", ex);
            }
        }
    }
}
